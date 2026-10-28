"""Account-scoped recruiter workflow. No endpoint sends an unapproved draft."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import gmail
from .database import get_db
from .models import GmailConnection, GmailOAuthState, OutreachContact, OutreachMessage, OutreachReply, OutreachSettings, now
from .outreach import OPT_OUT, content_digest, factual_draft, message_view, next_slot, preview_digest, profile_digest, reconcile_message, sender_settings
from .outreach_schemas import ContactInput, DraftInput, MessageApproval, MessageEdit, SenderSettings
from .schemas import ConsentInput
from .security import decrypt, digest, encrypt
from .services import enqueue, event, timestamp


def create_router(current_user,require_locked_session):
    router = APIRouter(prefix="/api/outreach",tags=["Recruiter outreach"])

    @router.get("")
    def overview(user=Depends(current_user),db:Session=Depends(get_db)):
        connection = db.get(GmailConnection,user.id)
        contacts = list(db.scalars(select(OutreachContact).where(OutreachContact.owner_id==user.id).order_by(OutreachContact.created_at.desc()).limit(200)))
        messages = list(db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id==user.id).order_by(OutreachMessage.created_at.desc()).limit(100)))
        counts = dict(db.execute(select(OutreachMessage.status,func.count()).where(OutreachMessage.owner_id==user.id).group_by(OutreachMessage.status)).all())
        replies = list(db.scalars(select(OutreachReply).where(OutreachReply.owner_id==user.id).order_by(OutreachReply.received_at.desc()).limit(100)))
        return {"gmail_configured":gmail.configured(),"connection":None if not connection else {"email":decrypt(connection.data_encrypted)["email"],"status":connection.status,"last_sync_at":connection.last_sync_at},
                "settings":sender_settings(db,user.id),"contacts":[{"id":row.id,"status":row.status,**decrypt(row.data_encrypted)} for row in contacts],
                "messages":[message_view(row) for row in messages],"counts":counts,"contacts_total":db.scalar(select(func.count()).select_from(OutreachContact).where(OutreachContact.owner_id==user.id)),
                "replies":[{"id":row.id,"contact_id":row.contact_id,"kind":row.kind,"received_at":row.received_at,**decrypt(row.data_encrypted)} for row in replies],
                "limits":{"contacts_shown":200,"messages_shown":100,"replies_shown":100,"daily_maximum":40}}

    @router.put("/settings")
    def update_settings(data:SenderSettings,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        require_locked_session(request,user,db)
        if data.enabled and not db.get(GmailConnection,user.id):
            raise HTTPException(409,"Connect a verified Gmail sender before enabling scheduled outreach")
        row = db.get(OutreachSettings,user.id)
        if row:
            row.data_encrypted = encrypt(data.model_dump())
        else:
            db.add(OutreachSettings(owner_id=user.id,data_encrypted=encrypt(data.model_dump())))
        event(db,user.id,"outreach_settings","Sender policy updated; individual message approvals remain required")
        db.commit()
        return data.model_dump()

    @router.post("/gmail/connect")
    def connect(data:ConsentInput,request:Request,response:Response,user=Depends(current_user),db:Session=Depends(get_db)):
        if not data.consent:
            raise HTTPException(422,"Consent to Gmail send and known-thread reply tracking is required")
        require_locked_session(request,user,db)
        token = request.cookies.get("internpilot_session","")
        from .config import settings
        # Refresh cookie attributes for installations whose existing login was
        # issued with SameSite=Strict before OAuth support was installed.
        lifetime = max(0,int((timestamp(request.state.session.expires_at)-datetime.now(timezone.utc)).total_seconds()))
        response.set_cookie("internpilot_session",token,httponly=True,secure=settings.cookie_secure,samesite="lax",max_age=lifetime,path="/")
        return {"authorization_url":gmail.start_authorization(db,user.id,token)}

    @router.get("/gmail/callback")
    async def callback(request:Request,state:str=Query(...,min_length=20,max_length=200),code:str|None=Query(None,min_length=1,max_length=2048),error:str|None=Query(None,max_length=200),user=Depends(current_user),db:Session=Depends(get_db)):
        if error or not code:
            pending=db.get(GmailOAuthState,digest(state))
            if not pending or pending.owner_id!=user.id or pending.session_hash!=digest(request.cookies.get("internpilot_session","")) or pending.expires_at<=now():
                raise HTTPException(400,"OAuth state is invalid or expired")
            db.delete(pending)
            event(db,user.id,"gmail_authorization_cancelled","Google authorization was cancelled; no sender connected")
            db.commit()
            return RedirectResponse("/?view=outreach",status_code=303)
        await gmail.finish_authorization(db,user.id,request.cookies.get("internpilot_session",""),state,code)
        event(db,user.id,"gmail_connected","Verified Gmail sender connected with encrypted offline tokens")
        db.commit()
        return RedirectResponse("/?view=outreach",status_code=303)

    @router.delete("/gmail")
    def disconnect(data:ConsentInput,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        if not data.consent:
            raise HTTPException(422,"Confirm disconnecting this Gmail account")
        require_locked_session(request,user,db)
        db.execute(delete(GmailConnection).where(GmailConnection.owner_id==user.id))
        db.execute(delete(GmailOAuthState).where(GmailOAuthState.owner_id==user.id))
        for row in db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id==user.id,OutreachMessage.status=="approved")):
            row.status,row.reason = "needs_review","Gmail disconnected; approval revoked"
        event(db,user.id,"gmail_disconnected","Local Gmail tokens removed. Google account permissions can be revoked in Google Account settings.")
        db.commit()
        return {"disconnected":True,"note":"Local tokens removed. Revoke the app under your Google Account's third-party access to invalidate the provider grant."}

    @router.post("/contacts")
    def add_contact(data:ContactInput,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        require_locked_session(request,user,db)
        if db.scalar(select(OutreachContact.id).where(OutreachContact.owner_id==user.id,OutreachContact.email_hash==digest(data.email))):
            raise HTTPException(409,"This contact already exists; opt-outs cannot be bypassed by re-adding an address")
        if db.scalar(select(func.count()).select_from(OutreachContact).where(OutreachContact.owner_id==user.id))>=2000:
            raise HTTPException(409,"Contact quota reached (2,000 per account)")
        row = OutreachContact(owner_id=user.id,email_hash=digest(data.email),data_encrypted=encrypt(data.model_dump()))
        db.add(row);db.flush()
        event(db,user.id,"outreach_contact","Verified recruiter contact saved from a user-provided source")
        db.commit()
        return {"id":row.id,"status":row.status,**data.model_dump()}

    @router.post("/contacts/{contact_id}/opt-out")
    def opt_out(contact_id:str,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        require_locked_session(request,user,db)
        row = db.get(OutreachContact,contact_id)
        if not row or row.owner_id!=user.id:
            raise HTTPException(404,"Contact not found")
        row.status = "opted_out"
        for message in db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id==user.id,OutreachMessage.contact_id==row.id,OutreachMessage.status.in_(["draft","approved","needs_review"]))):
            message.status,message.reason = "cancelled","Contact opted out"
        event(db,user.id,"outreach_opt_out","Contact opted out; pending messages cancelled")
        db.commit()
        return {"status":row.status}

    @router.post("/messages")
    def draft(data:DraftInput,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        user = require_locked_session(request,user,db)
        contact = db.get(OutreachContact,data.contact_id)
        if not contact or contact.owner_id!=user.id:
            raise HTTPException(404,"Contact not found")
        if contact.status!="active" or db.scalar(select(OutreachReply.id).where(OutreachReply.owner_id==user.id,OutreachReply.contact_id==contact.id)):
            raise HTTPException(409,"A reply, opt-out or bounce prevents further outreach")
        existing = list(db.scalars(select(OutreachMessage).where(OutreachMessage.owner_id==user.id,OutreachMessage.contact_id==contact.id)))
        if any(row.status in {"draft","approved","sending","uncertain","needs_review"} for row in existing):
            raise HTTPException(409,"An existing draft or unresolved send already exists for this contact")
        policy = sender_settings(db,user.id)
        today = datetime.now(timezone.utc).date().isoformat()
        if db.scalar(select(func.count()).select_from(OutreachMessage).where(OutreachMessage.owner_id==user.id,OutreachMessage.created_at>=today))>=100:
            raise HTTPException(409,"Daily draft quota reached (100 per account)")
        if data.parent_id:
            parent = db.get(OutreachMessage,data.parent_id)
            if not parent or parent.owner_id!=user.id or parent.contact_id!=contact.id or parent.status!="sent" or not parent.sent_at:
                raise HTTPException(409,"A confirmed sent parent message is required for a follow-up")
            if timestamp(parent.sent_at)>datetime.now(timezone.utc)-timedelta(days=policy["followup_days"]):
                raise HTTPException(409,"Wait for the configured follow-up interval")
            if len([row for row in existing if row.parent_id])>=2:
                raise HTTPException(409,"The maximum of two follow-ups has been reached")
        elif any(row.status=="sent" for row in existing):
            raise HTTPException(409,"Use a reviewed follow-up rather than another initial email")
        content = factual_draft(decrypt(user.profile_encrypted),decrypt(contact.data_encrypted),policy,followup=bool(data.parent_id))
        row = OutreachMessage(owner_id=user.id,contact_id=contact.id,parent_id=data.parent_id,content_encrypted=encrypt(content))
        db.add(row);db.flush()
        event(db,user.id,"outreach_draft","Factual outreach draft created; no message sent")
        db.commit()
        return message_view(row)

    def owned(db,user,message_id):
        row = db.get(OutreachMessage,message_id)
        if not row or row.owner_id!=user.id:
            raise HTTPException(404,"Message not found")
        return row

    @router.put("/messages/{message_id}")
    def edit(message_id:str,data:MessageEdit,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        user = require_locked_session(request,user,db)
        row = owned(db,user,message_id)
        if row.sending_started_at or row.status not in {"draft","needs_review","approved"}:
            raise HTTPException(409,"Only unsent drafts can be edited")
        content = decrypt(row.content_encrypted)
        body=data.body if OPT_OUT in data.body else data.body+"\n\n"+OPT_OUT
        if len(body)>6000:
            raise HTTPException(422,"Shorten the message to leave room for the opt-out footer")
        content.update(subject=data.subject,body=body,profile_digest=profile_digest(decrypt(user.profile_encrypted)))
        row.content_encrypted,row.status,row.approved_at,row.approval_digest,row.updated_at = encrypt(content),"draft",None,None,now()
        row.reason = "Edited factual draft; fresh approval is required"
        event(db,user.id,"outreach_edited",row.reason)
        db.commit()
        return message_view(row)

    @router.post("/messages/{message_id}/approve")
    def approve(message_id:str,data:MessageApproval,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        user = require_locked_session(request,user,db)
        row = owned(db,user,message_id)
        if row.sending_started_at or row.status not in {"draft","needs_review","approved"}:
            raise HTTPException(409,"This message is not available for approval")
        connection,contact = db.get(GmailConnection,user.id),db.get(OutreachContact,row.contact_id)
        if not connection or connection.status!="connected":
            raise HTTPException(409,"Connect Gmail before approving a scheduled message")
        if not contact or contact.status!="active" or db.scalar(select(OutreachReply.id).where(OutreachReply.owner_id==user.id,OutreachReply.contact_id==contact.id)):
            raise HTTPException(409,"The contact has replied, bounced or opted out")
        if decrypt(user.policy_encrypted).get("emergency_stop"):
            raise HTTPException(409,"Emergency stop is active")
        content,profile = decrypt(row.content_encrypted),decrypt(user.profile_encrypted)
        if data.preview_digest!=preview_digest(content):
            raise HTTPException(409,"This draft changed after your preview. Reload it and review the exact current message before approval")
        if content.get("profile_digest")!=profile_digest(profile):
            raise HTTPException(409,"Your profile changed. Regenerate or review and save the message against your current verified facts")
        scheduled = timestamp(data.scheduled_at) or datetime.now(timezone.utc)
        if scheduled>datetime.now(timezone.utc)+timedelta(days=90):
            raise HTTPException(422,"Schedule messages at most 90 days ahead")
        row.approval_digest = content_digest(content,profile,connection)
        row.approved_at,row.scheduled_at,row.status,row.updated_at = now(),next_slot(sender_settings(db,user.id),scheduled).isoformat(),"approved",now()
        row.reason = "Specific message approved; sender policy, gaps, limits and reply checks still apply"
        event(db,user.id,"outreach_approved",row.reason)
        db.commit()
        return message_view(row)

    @router.post("/messages/{message_id}/cancel")
    def cancel(message_id:str,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        require_locked_session(request,user,db)
        row = owned(db,user,message_id)
        if row.sending_started_at:
            raise HTTPException(409,"Sending already started; inspect or reconcile its outcome")
        row.status,row.reason,row.updated_at = "cancelled","Cancelled by candidate",now()
        event(db,user.id,"outreach_cancelled",row.reason)
        db.commit()
        return message_view(row)

    @router.post("/messages/{message_id}/reconcile")
    async def reconcile(message_id:str,data:ConsentInput,user=Depends(current_user),db:Session=Depends(get_db)):
        if not data.consent:
            raise HTTPException(422,"Approve inspecting Gmail for this message's receipt")
        owned(db,user,message_id)
        return await reconcile_message(user.id,message_id)

    @router.post("/sync")
    def sync(data:ConsentInput,user=Depends(current_user),db:Session=Depends(get_db)):
        if not data.consent or not db.get(GmailConnection,user.id):
            raise HTTPException(409,"Connect Gmail and approve known-thread reply synchronization")
        task = enqueue(db,user.id,"gmail_sync",{},"gmail-sync:"+user.id)
        db.commit()
        return {"task_id":task.id,"status":task.status}

    return router
