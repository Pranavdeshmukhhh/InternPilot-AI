"""Specific-message outreach approvals, bounded sending and conservative receipts.

Draft creation and follow-up creation never send mail. Each message is approved
against its exact content, recipient, verified profile and connected sender.
"""
import base64
import json
import re
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, getaddresses, parseaddr
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select

from . import gmail
from .account_security import locked_user
from .database import SessionLocal
from .models import GmailConnection, OutreachContact, OutreachMessage, OutreachReply, OutreachSettings, User, now
from .outreach_schemas import SenderSettings
from .security import decrypt, digest, encrypt
from .services import enqueue, event, timestamp

OPT_OUT = "If you'd prefer no further messages, reply 'stop' and I won't follow up."


def sender_settings(db,owner_id):
    row = db.get(OutreachSettings,owner_id)
    return SenderSettings.model_validate(decrypt(row.data_encrypted) if row else {}).model_dump()


def next_slot(policy,at=None):
    at = at or datetime.now(timezone.utc)
    zone = ZoneInfo(policy["timezone"])
    for _ in range(10):
        local = at.astimezone(zone)
        if policy["weekdays_only"] and local.weekday()>=5:
            local = (local+timedelta(days=1)).replace(hour=policy["start_hour"],minute=0,second=0,microsecond=0)
        elif local.hour<policy["start_hour"]:
            local = local.replace(hour=policy["start_hour"],minute=0,second=0,microsecond=0)
        elif local.hour>=policy["end_hour"]:
            local = (local+timedelta(days=1)).replace(hour=policy["start_hour"],minute=0,second=0,microsecond=0)
        else:
            return at
        at = local.astimezone(timezone.utc)
    raise ValueError("No sending window is available")


def content_digest(content,profile,connection):
    sender = decrypt(connection.data_encrypted)["email"] if connection else None
    return digest(json.dumps({"content":content,"profile":profile,"sender":sender},sort_keys=True,default=str))


def profile_digest(profile):
    return digest(json.dumps(profile,sort_keys=True,default=str))


def preview_digest(content):
    return digest(json.dumps(content,sort_keys=True,default=str))


def message_view(row):
    content=decrypt(row.content_encrypted)
    return {"id":row.id,"contact_id":row.contact_id,"parent_id":row.parent_id,"status":row.status,"reason":row.reason,
            "scheduled_at":row.scheduled_at,"sent_at":row.sent_at,"provider_id":row.provider_id,"thread_id":row.thread_id,
            "created_at":row.created_at,"updated_at":row.updated_at,**content,"preview_digest":preview_digest(content)}


def factual_draft(profile,contact,policy,*,followup=False):
    fields = set(profile.get("verified_fields",[]))
    projects = profile.get("projects",[]) if "projects" in fields else []
    relevant = [item for item in projects if isinstance(item,dict) and isinstance(item.get("name"),str) and isinstance(item.get("description"),str) and item["name"].strip() and item["description"].strip()]
    target = set(re.findall(r"[a-z]{3,}",(contact.get("role","")+" "+contact.get("employer_fact","")).casefold()))
    project = max(relevant,key=lambda item:len(target & set(re.findall(r"[a-z]{3,}",(item["name"]+" "+item["description"]+" "+" ".join(map(str,item.get("skills",[])))).casefold())))) if relevant else None
    if "name" not in fields or not profile.get("name") or project is None:
        raise HTTPException(422,"Verify your name and at least one factual project in Candidate profile before generating outreach")
    school = ""
    if {"degree","university"}.issubset(fields) and profile.get("degree") and profile.get("university"):
        school = f", studying {profile['degree']} at {profile['university']}"
    values = {"name":profile["name"],"contact_name":contact["name"],"company":contact["company"],"role":contact["role"],
              "project":str(project["name"]),"project_summary":str(project["description"])[:700],"employer_fact":contact.get("employer_fact","")}
    subject = f"{contact['role']} at {contact['company']} — {profile['name']}"[:200]
    greeting = "Dear" if policy["tone"]=="formal" else "Hi" if policy["tone"]=="friendly" else "Hello"
    body = f"{greeting} {contact['name']},\n\nI'm {profile['name']}{school}. I'm interested in {contact['role']} opportunities at {contact['company']}.\n\nMy project {values['project']}: {values['project_summary']}"
    if contact.get("employer_fact"):
        body += "\n\n"+contact["employer_fact"]
    body += "\n\nWould you be the right person to ask about relevant student opportunities, or could you point me to the official application?"
    if followup:
        subject = "Re: "+subject[:196]
        body = f"{greeting} {contact['name']},\n\nA brief follow-up on my interest in {contact['role']} opportunities at {contact['company']}. If there is a relevant opening, I'd appreciate a link to the official application. Thank you for your time."
    for field in ("subject_template","body_template"):
        template = policy[field]
        if template and not followup:
            if any(key not in values for key in re.findall(r"\{([^{}]*)\}",template)):
                raise HTTPException(422,"Template placeholders must use the documented factual fields")
            try:
                rendered = template.format_map(values)
            except (KeyError,ValueError,AttributeError):
                raise HTTPException(422,"Template placeholders are invalid") from None
            if field=="subject_template":
                subject = rendered
            else:
                body = rendered
    body += "\n\n"+(policy["signature"] or profile["name"])
    body += "\n\n"+OPT_OUT
    if len(subject)>200 or any(c in subject for c in "\r\n") or len(body)>6000:
        raise HTTPException(422,"Generated message exceeds subject/body limits; shorten the template or signature")
    return {"subject":subject,"body":body,"recipient":contact["email"],"company":contact["company"],"profile_digest":profile_digest(profile)}


def schedule_outreach():
    with SessionLocal() as db:
        due = db.scalars(select(OutreachMessage).where(OutreachMessage.status=="approved",OutreachMessage.scheduled_at<=now()).order_by(OutreachMessage.scheduled_at).limit(200))
        for row in due:
            enqueue(db,row.owner_id,"outreach",{"message_id":row.id},"outreach:"+row.id)
        for connection in db.scalars(select(GmailConnection).where(GmailConnection.status=="connected").limit(1000)):
            if not connection.last_sync_at or timestamp(connection.last_sync_at)<datetime.now(timezone.utc)-timedelta(minutes=15):
                enqueue(db,connection.owner_id,"gmail_sync",{},"gmail-sync:"+connection.owner_id)
        db.commit()


async def send_message(message_id,*,task_id=None,lease_owner=None):
    from .services import valid_lease
    with SessionLocal() as db:
        candidate = db.get(OutreachMessage,message_id)
        followup_owner = candidate.owner_id if candidate and candidate.parent_id and candidate.status == "approved" and not candidate.sending_started_at else None
    if followup_owner:
        try:
            await refresh_followup_recipient(followup_owner, message_id)
        except Exception:
            with SessionLocal() as db:
                row = db.get(OutreachMessage, message_id)
                if row and row.status == "approved" and not row.sending_started_at:
                    row.status, row.reason = "needs_review", "Recipient thread verification failed; review before approving again"
                    db.commit()
            return
    with SessionLocal() as db:
        row = db.get(OutreachMessage,message_id)
        if not row or row.status!="approved" or row.sending_started_at:
            return
        user = locked_user(db,user_id=row.owner_id)
        row = db.scalar(select(OutreachMessage).where(OutreachMessage.id==message_id).with_for_update().execution_options(populate_existing=True))
        if not row or row.status!="approved" or row.sending_started_at:
            return
        if not user or user.disabled or decrypt(user.policy_encrypted).get("emergency_stop"):
            return
        if not valid_lease(db,task_id,lease_owner):
            return
        contact,connection = db.get(OutreachContact,row.contact_id),db.get(GmailConnection,row.owner_id)
        policy,content = sender_settings(db,row.owner_id),decrypt(row.content_encrypted)
        if not policy["enabled"]:
            return
        if not contact or contact.status!="active":
            row.status,row.reason = "cancelled","Contact is no longer eligible for outreach"
            db.commit();return
        if not connection or connection.status!="connected":
            row.status,row.reason = "needs_review","Reconnect Gmail before approving this message again"
            db.commit();return
        if row.approval_digest!=content_digest(content,decrypt(user.profile_encrypted),connection) or content["recipient"]!=decrypt(contact.data_encrypted)["email"]:
            row.status,row.reason = "needs_review","Candidate facts, recipient or sender changed; review and approve again"
            db.commit();return
        if db.scalar(select(OutreachReply.id).where(OutreachReply.owner_id==row.owner_id,OutreachReply.contact_id==row.contact_id)):
            row.status,row.reason = "cancelled","A reply, opt-out or bounce stopped further outreach"
            db.commit();return
        instant = datetime.now(timezone.utc)
        zone = ZoneInfo(policy["timezone"])
        since = instant.astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
        used = db.scalar(select(func.count()).select_from(OutreachMessage).where(OutreachMessage.owner_id==row.owner_id,OutreachMessage.sending_started_at>=since.isoformat()))
        earliest = max(instant,timestamp(row.scheduled_at) or instant)
        if connection.last_reserved_at:
            earliest = max(earliest,timestamp(connection.last_reserved_at)+timedelta(minutes=policy["gap_minutes"]))
        if used>=policy["daily_limit"]:
            earliest = max(earliest,(since.astimezone(zone)+timedelta(days=1)).replace(hour=policy["start_hour"]).astimezone(timezone.utc))
        earliest = next_slot(policy,earliest)
        if earliest>instant+timedelta(seconds=1):
            row.scheduled_at,row.reason = earliest.isoformat(),"Waiting for sender window, quota or minimum gap"
            db.commit();return
        identity = decrypt(connection.data_encrypted)["email"]
        mail = EmailMessage()
        mail["From"],mail["To"],mail["Subject"],mail["Message-ID"] = identity,content["recipient"],content["subject"],row.rfc_message_id
        mail["Date"]=format_datetime(instant)
        mail["List-Unsubscribe"] = f"<mailto:{identity}?subject=Stop%20outreach>"
        mail.set_content(content["body"])
        payload = {"raw":base64.urlsafe_b64encode(mail.as_bytes()).decode()}
        if row.parent_id:
            parent = db.get(OutreachMessage,row.parent_id)
            if not parent or not parent.thread_id:
                row.status,row.reason = "needs_review","Parent thread is unavailable"
                db.commit();return
            mail["In-Reply-To"],mail["References"] = parent.rfc_message_id,parent.rfc_message_id
            payload = {"raw":base64.urlsafe_b64encode(mail.as_bytes()).decode(),"threadId":parent.thread_id}
        row.status,row.sending_started_at,row.updated_at = "sending",now(),now()
        connection.last_reserved_at = row.sending_started_at
        owner_id = row.owner_id
        event(db,owner_id,"outreach_send_started","Approved message checkpoint persisted before Gmail request")
        db.commit()
    try:
        receipt = await gmail.request(owner_id,"POST","messages/send",payload=payload)
        if not receipt.get("id") or not receipt.get("threadId"):
            raise ValueError("No Gmail receipt")
        with SessionLocal() as db:
            row = db.get(OutreachMessage,message_id)
            row.status,row.provider_id,row.thread_id,row.sent_at,row.updated_at = "sent",str(receipt["id"])[:255],str(receipt["threadId"])[:255],now(),now()
            row.reason = "Gmail accepted this message; recipient delivery is not confirmed"
            event(db,owner_id,"outreach_sent",row.reason,notify=True)
            db.commit()
    except Exception:
        with SessionLocal() as db:
            row = db.get(OutreachMessage,message_id)
            row.status,row.reason,row.updated_at = "uncertain","Send checkpoint reached without a complete provider receipt. Reconcile before another action.",now()
            event(db,owner_id,"outreach_uncertain",row.reason,notify=True)
            db.commit()


def _plain_payload(payload):
    result = []
    pending = [payload]
    for _ in range(30):
        if not pending:
            break
        part = pending.pop()
        pending.extend((part.get("parts") or [])[:20])
        if part.get("mimeType") in {"message/rfc822","text/rfc822-headers"}:
            result.extend(str(header.get("name",""))+": "+str(header.get("value","")) for header in part.get("headers",[]) if str(header.get("name","")).casefold() in {"message-id","to","final-recipient"})
        if part.get("mimeType") in {"text/plain","message/delivery-status","text/rfc822-headers"}:
            data = str((part.get("body") or {}).get("data") or "")[:16000]
            try:
                result.append(base64.urlsafe_b64decode(data+"="*(-len(data)%4)).decode("utf-8",errors="replace")[:8000])
            except (ValueError,TypeError):
                pass
    return "\n".join(result)[:16000]


async def refresh_followup_recipient(owner_id, message_id):
    """Fail closed unless this recipient's actual prior threads were inspected.

    A rotating background page cannot authorize sending. All known contact
    threads are checked (up to 25); oversized/unsupported responses require
    human review. The subsequent transaction rechecks persisted suppression.
    """
    with SessionLocal() as db:
        row = db.get(OutreachMessage, message_id)
        if not row or row.owner_id != owner_id or not row.parent_id:
            raise ValueError("Follow-up is unavailable")
        parent = db.get(OutreachMessage, row.parent_id)
        connection = db.get(GmailConnection, owner_id)
        if not parent or parent.owner_id != owner_id or parent.contact_id != row.contact_id or parent.status != "sent" or not parent.provider_id or not parent.thread_id or not connection or connection.status != "connected":
            raise ValueError("Parent thread or sender is unavailable")
        rows = list(db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id == owner_id,
            OutreachMessage.contact_id == row.contact_id, OutreachMessage.thread_id != None)
            .order_by(OutreachMessage.id).limit(1001)))
        threads = {sent.thread_id: sent for sent in rows}
        if len(rows) > 1000 or len(threads) > 25:
            raise ValueError("Recipient history exceeds the safe verification budget")
        identity = decrypt(connection.data_encrypted)["email"]
        sent_ids = {sent.provider_id for sent in rows}
    await _sync_threads(owner_id, list(threads.values()), identity, sent_ids, require_sent_evidence=True)


async def _sync_threads(owner_id, selected, identity, sent_ids, *, require_sent_evidence=False):
    for sent in selected:
        thread = await gmail.request(owner_id,"GET","threads/"+str(sent.thread_id),params={"format":"full"})
        messages = thread.get("messages")
        if not isinstance(messages, list) or len(messages) > 1000 or any(not isinstance(item, dict) or not item.get("id") or not isinstance(item.get("payload"), dict) for item in messages):
            raise ValueError("Thread inventory could not be verified completely")
        if require_sent_evidence and (thread.get("id") != sent.thread_id or not sent.provider_id or sent.provider_id not in {message["id"] for message in messages}):
            raise ValueError("The thread did not confirm the known sent message")
        for reply in messages:
            if not isinstance(reply,dict) or not reply.get("id") or reply["id"] in sent_ids:
                continue
            payload = reply.get("payload") or {}
            headers = {str(h.get("name","")).casefold():str(h.get("value","")) for h in payload.get("headers",[]) if isinstance(h,dict)}
            addresses = {address.casefold() for _,address in getaddresses([headers.get("from","")])}
            if not addresses and require_sent_evidence:
                raise ValueError("Thread sender metadata is incomplete")
            if identity in addresses or not addresses:
                continue
            body = _plain_payload(payload)
            with SessionLocal() as db:
                if db.scalar(select(OutreachReply.id).where(OutreachReply.owner_id==owner_id,OutreachReply.provider_id==str(reply["id"]))):
                    continue
                contact = db.get(OutreachContact,sent.contact_id)
                if not contact or contact.owner_id != owner_id:
                    raise ValueError("Recipient is unavailable")
                address = decrypt(contact.data_encrypted)["email"]
                bounce = any("mailer-daemon@" in item or "postmaster@" in item for item in addresses) and (address.casefold() in body.casefold() or sent.rfc_message_id in body)
                # Gmail thread membership alone does not authorize unrelated senders
                # to change a contact's status. Restrict to the verified contact or DSN.
                if address not in addresses and not bounce:
                    continue
                optout = bool(re.search(r"\b(?:unsubscribe|remove me|do not contact|don't contact|stop emailing|stop sending)\b|^\s*stop\s*[.!]?\s*$",body.split("\nOn ")[0],re.I))
                kind = "bounce" if bounce else "opt_out" if optout else "reply"
                received = now()
                try:
                    received = datetime.fromtimestamp(int(reply.get("internalDate"))/1000,timezone.utc).isoformat()
                except (ValueError,TypeError,OverflowError):
                    pass
                db.add(OutreachReply(owner_id=owner_id,contact_id=contact.id,provider_id=str(reply["id"]),kind=kind,data_encrypted=encrypt({"from":parseaddr(headers.get("from",""))[1],"subject":headers.get("subject","")[:300],"excerpt":body[:2000]}),received_at=received))
                if kind in {"bounce","opt_out"}:
                    contact.status = "bounced" if bounce else "opted_out"
                for pending in db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id==owner_id,OutreachMessage.contact_id==contact.id,OutreachMessage.status.in_(["draft","approved","needs_review"]))):
                    pending.status,pending.reason = "cancelled","A reply, bounce or opt-out stopped outreach"
                event(db,owner_id,"outreach_"+kind,"Recruiter thread updated; further outreach stopped",notify=True)
                db.commit()


async def sync_replies(owner_id):
    """Inspect only known outreach threads; bounded rotating pages, never the whole inbox."""
    with SessionLocal() as db:
        connection = db.get(GmailConnection,owner_id)
        user = db.get(User,owner_id)
        if not connection or not user or user.disabled or connection.status!="connected":
            return
        rows = list(db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id==owner_id,OutreachMessage.thread_id!=None).order_by(OutreachMessage.created_at)))
        if not rows:
            connection.last_sync_at = now();db.commit()
            await sync_bounces(owner_id)
            return
        start = connection.sync_cursor%len(rows)
        selected = (rows[start:]+rows[:start])[:25]
        connection.sync_cursor = (start+len(selected))%len(rows)
        sent_ids = {row.provider_id for row in rows}
        identity = decrypt(connection.data_encrypted)["email"]
        db.commit()
    await _sync_threads(owner_id, selected, identity, sent_ids)
    await sync_bounces(owner_id)
    with SessionLocal() as db:
        row = db.get(GmailConnection,owner_id)
        if row:
            row.last_sync_at = now();db.commit()


async def sync_bounces(owner_id):
    """Read bounded DSN pages and match both original Message-ID and recipient."""
    with SessionLocal() as db:
        connection=db.get(GmailConnection,owner_id)
        if not connection or connection.status!="connected":
            return
        cursor=decrypt(connection.data_encrypted).get("bounce_page_token")
        rows=list(db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id==owner_id,OutreachMessage.sending_started_at!=None)))
    if not rows:
        return
    params={"q":"newer_than:30d {from:mailer-daemon from:postmaster}","maxResults":25}
    if cursor:
        params["pageToken"]=cursor
    listing=await gmail.request(owner_id,"GET","messages",params=params)
    for reference in (listing.get("messages") or [])[:25]:
        if not isinstance(reference,dict) or not reference.get("id"):
            continue
        provider_id=str(reference["id"])
        with SessionLocal() as db:
            if db.scalar(select(OutreachReply.id).where(OutreachReply.owner_id==owner_id,OutreachReply.provider_id==provider_id)):
                continue
        message=await gmail.request(owner_id,"GET","messages/"+provider_id,params={"format":"full"})
        payload=message.get("payload") or {}
        headers={str(h.get("name","")).casefold():str(h.get("value","")) for h in payload.get("headers",[]) if isinstance(h,dict)}
        senders={address.casefold() for _,address in getaddresses([headers.get("from","")])}
        if not any("mailer-daemon@" in address or "postmaster@" in address for address in senders):
            continue
        body=_plain_payload(payload)
        for original in rows:
            if original.rfc_message_id not in body:
                continue
            with SessionLocal() as db:
                contact=db.get(OutreachContact,original.contact_id)
                if not contact or decrypt(contact.data_encrypted)["email"].casefold() not in body.casefold():
                    continue
                if db.scalar(select(OutreachReply.id).where(OutreachReply.owner_id==owner_id,OutreachReply.provider_id==provider_id)):
                    break
                db.add(OutreachReply(owner_id=owner_id,contact_id=contact.id,provider_id=provider_id,kind="bounce",data_encrypted=encrypt({"from":headers.get("from",""),"subject":headers.get("subject","")[:300],"excerpt":body[:2000]})))
                contact.status="bounced"
                for pending in db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id==owner_id,OutreachMessage.contact_id==contact.id,OutreachMessage.status.in_(["draft","approved","needs_review"]))):
                    pending.status,pending.reason="cancelled","A matched delivery-status notice stopped outreach"
                event(db,owner_id,"outreach_bounce","A matched Gmail delivery-status notice stopped further outreach",notify=True)
                db.commit()
            break
    with SessionLocal() as db:
        connection=db.get(GmailConnection,owner_id)
        if connection:
            content=decrypt(connection.data_encrypted)
            content["bounce_page_token"]=listing.get("nextPageToken")
            connection.data_encrypted=encrypt(content)
            db.commit()


async def reconcile_message(owner_id,message_id):
    with SessionLocal() as db:
        row = db.get(OutreachMessage,message_id)
        if not row or row.owner_id!=owner_id or row.status!="uncertain":
            raise HTTPException(409,"Only an uncertain message can be reconciled")
        rfc_id = row.rfc_message_id
    result = await gmail.request(owner_id,"GET","messages",params={"q":"in:sent rfc822msgid:"+rfc_id,"maxResults":2})
    matches = result.get("messages") or []
    if len(matches)!=1 or not matches[0].get("id") or not matches[0].get("threadId"):
        return {"status":"uncertain","reason":"No unique Gmail sent receipt was found. No retry was performed."}
    metadata = await gmail.request(owner_id,"GET","messages/"+str(matches[0]["id"]),params={"format":"metadata","metadataHeaders":["Message-ID","To"]})
    headers = {str(header.get("name","")).casefold():str(header.get("value","")) for header in (metadata.get("payload") or {}).get("headers",[]) if isinstance(header,dict)}
    with SessionLocal() as db:
        expected_recipient = decrypt(db.get(OutreachMessage,message_id).content_encrypted)["recipient"]
    recipients = {address.casefold() for _,address in getaddresses([headers.get("to","")])}
    if headers.get("message-id")!=rfc_id or expected_recipient not in recipients or "SENT" not in metadata.get("labelIds",[]) or metadata.get("threadId")!=matches[0]["threadId"]:
        return {"status":"uncertain","reason":"The found message did not verify the exact recipient and sent Message-ID. No retry was performed."}
    with SessionLocal() as db:
        row = db.get(OutreachMessage,message_id)
        row.status,row.provider_id,row.thread_id,row.updated_at = "sent",str(matches[0]["id"]),str(matches[0]["threadId"]),now()
        row.reason = "Recovered Gmail sent receipt; provider acceptance confirmed, delivery not confirmed"
        try:
            row.sent_at = datetime.fromtimestamp(int(metadata["internalDate"])/1000,timezone.utc).isoformat()
        except (KeyError,TypeError,ValueError,OverflowError):
            pass  # Unknown send times remain unknown.
        event(db,owner_id,"outreach_reconciled",row.reason,notify=True)
        db.commit()
        return message_view(row)
