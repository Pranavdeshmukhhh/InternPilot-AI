"""Approved outbound notifications with a durable, single-attempt checkpoint.

Materializing drafts never sends a message. Every send requires fresh explicit
consent; deferred, failed and uncertain attempts are never sent by a scheduler.
"""
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
import hmac
import json
import os
import re
import smtplib
import ssl
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, exists, select, update
from sqlalchemy.exc import IntegrityError

from .models import Notification, NotificationDelivery, NotificationSettings, now
from .security import decrypt, digest, encrypt
from .services import event


DEFAULT_NOTIFICATION_SETTINGS = {
    "browser_enabled": False,
    "email_enabled": False,
    "email_to": "",
    "telegram_enabled": False,
    "telegram_chat_id": "",
    "whatsapp_enabled": False,
    "whatsapp_to": "",
    "quiet_hours_enabled": False,
    "quiet_start": "22:00",
    "quiet_end": "08:00",
    "timezone": "Asia/Kolkata",
}
CHANNEL_DESTINATIONS = {"email": "email_to", "telegram": "telegram_chat_id", "whatsapp": "whatsapp_to"}
_EMAIL = re.compile(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+")
_PHONE = re.compile(r"\+[1-9]\d{6,14}")
_CLOCK = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


def validate_notification_settings(settings):
    if not isinstance(settings, dict) or set(settings)-set(DEFAULT_NOTIFICATION_SETTINGS):
        raise HTTPException(422,"Notification settings contain unsupported fields")
    result = {**DEFAULT_NOTIFICATION_SETTINGS, **settings}
    for key in ("browser_enabled","email_enabled","telegram_enabled","whatsapp_enabled","quiet_hours_enabled"):
        if not isinstance(result[key],bool):
            raise HTTPException(422,"Notification switches must be true or false")
    for key in ("email_to","telegram_chat_id","whatsapp_to","quiet_start","quiet_end","timezone"):
        if not isinstance(result[key],str):
            raise HTTPException(422,"Notification destinations and quiet hours must be text")
        result[key] = result[key].strip()
    if result["email_to"] and (len(result["email_to"])>254 or not _EMAIL.fullmatch(result["email_to"])):
        raise HTTPException(422,"A valid notification email is required")
    if result["telegram_chat_id"] and not re.fullmatch(r"-?\d{1,20}",result["telegram_chat_id"]):
        raise HTTPException(422,"Telegram chat ID must be a numeric chat identifier")
    if result["whatsapp_to"] and not _PHONE.fullmatch(result["whatsapp_to"]):
        raise HTTPException(422,"WhatsApp number must include its international country code")
    for channel, destination in CHANNEL_DESTINATIONS.items():
        if result[channel+"_enabled"] and not result[destination]:
            raise HTTPException(422,f"A destination is required to enable {channel} notifications")
    if not _CLOCK.fullmatch(result["quiet_start"]) or not _CLOCK.fullmatch(result["quiet_end"]):
        raise HTTPException(422,"Quiet hours must use 24-hour HH:MM times")
    if result["quiet_hours_enabled"] and result["quiet_start"]==result["quiet_end"]:
        raise HTTPException(422,"Quiet hours must have different start and end times")
    try:
        if not result["timezone"] or len(result["timezone"])>100:
            raise ZoneInfoNotFoundError
        ZoneInfo(result["timezone"])
    except (ZoneInfoNotFoundError,ValueError):
        raise HTTPException(422,"Choose a valid IANA timezone") from None
    return result


def quiet_until(settings, at=None):
    """Return the quiet-hours end in UTC, with inclusive start/exclusive end."""
    settings = validate_notification_settings(settings)
    if not settings["quiet_hours_enabled"]:
        return None
    instant = at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    zone = ZoneInfo(settings["timezone"])
    local = instant.astimezone(zone)
    start, end = (time.fromisoformat(settings[key]) for key in ("quiet_start","quiet_end"))
    clock = local.time().replace(tzinfo=None)
    if start<end:
        if not start<=clock<end:
            return None
        day = local.date()
    elif clock>=start:
        day = local.date()+timedelta(days=1)
    elif clock<end:
        day = local.date()
    else:
        return None
    wall_end = datetime.combine(day,end)
    # Choose the later occurrence if a DST transition repeats the end time.
    return max(wall_end.replace(tzinfo=zone,fold=fold).astimezone(timezone.utc) for fold in (0,1))


def _smtp_config():
    try:
        port = int(os.getenv("SMTP_PORT","587"))
    except ValueError:
        return None
    host, sender = os.getenv("SMTP_HOST","").strip(), os.getenv("SMTP_FROM","").strip()
    username, password = os.getenv("SMTP_USER",""), os.getenv("SMTP_PASSWORD","")
    starttls = os.getenv("SMTP_STARTTLS","true").lower()=="true"
    if not host or not 1<=port<=65535 or not _EMAIL.fullmatch(sender) or bool(username)!=bool(password):
        return None
    if port!=465 and not starttls:
        return None
    return {"host":host,"port":port,"sender":sender,"username":username,"password":password,"starttls":starttls}


def delivery_config_status():
    """Configuration presence only; never exposes credentials or probes providers."""
    sender = os.getenv("TWILIO_WHATSAPP_FROM","").removeprefix("whatsapp:")
    return {
        "browser":True,
        "email":_smtp_config() is not None,
        "telegram":bool(os.getenv("TELEGRAM_BOT_TOKEN","").strip()),
        "whatsapp":bool(os.getenv("TWILIO_ACCOUNT_SID","") and os.getenv("TWILIO_AUTH_TOKEN","") and _PHONE.fullmatch(sender)),
    }


def _settings_digest(settings):
    return digest(json.dumps(settings,sort_keys=True,separators=(",",":")))


def delivery_view(row):
    payload = decrypt(row.payload_encrypted)
    return {key:getattr(row,key) for key in (
        "id","notification_id","channel","status","approved_at","not_before",
        "attempts","last_error","provider_id","created_at","updated_at",
    )} | {"message":payload["message"],"destination":payload["destination"]}


def materialize_delivery_drafts(db, owner_id=None):
    """Create at most 500 unseen drafts per owner/channel. Caller commits."""
    # Provider calls have a short bounded timeout. A process lost after the
    # durable send checkpoint cannot establish whether the provider accepted.
    cutoff = (datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
    abandoned = select(NotificationDelivery).where(NotificationDelivery.status=="sending",NotificationDelivery.updated_at<cutoff)
    if owner_id is not None:
        abandoned = abandoned.where(NotificationDelivery.owner_id==owner_id)
    for pending in db.scalars(abandoned.with_for_update(skip_locked=True)).all():
        pending.status,pending.updated_at = "uncertain",now()
        pending.last_error = "Delivery process stopped after the send checkpoint; reconcile with the provider before any further message"
        event(db,pending.owner_id,"notification_uncertain",pending.last_error)
    query = select(NotificationSettings)
    if owner_id is not None:
        query = query.where(NotificationSettings.owner_id==owner_id)
    configured = delivery_config_status()
    count = 0
    for preference in db.scalars(query).all():
        settings = validate_notification_settings(decrypt(preference.settings_encrypted))
        settings_digest = _settings_digest(settings)
        for channel, destination in CHANNEL_DESTINATIONS.items():
            if not settings[channel+"_enabled"] or not configured[channel]:
                continue
            stale_ids = []
            for pending in db.scalars(select(NotificationDelivery).where(
                NotificationDelivery.owner_id==preference.owner_id,NotificationDelivery.channel==channel,
                NotificationDelivery.status=="draft",NotificationDelivery.attempts==0,
                NotificationDelivery.approved_at.is_(None),
            ).limit(500)).all():
                snapshot = decrypt(pending.payload_encrypted)
                if snapshot.get("settings_digest")!=settings_digest:
                    stale_ids.append(pending.id)
            if stale_ids:
                # Rebuild with a NEW identifier so approval of an old preview
                # cannot send a changed destination/body. Recheck draft state
                # in the DELETE in case another request already began sending.
                db.execute(delete(NotificationDelivery).where(
                    NotificationDelivery.id.in_(stale_ids),NotificationDelivery.status=="draft",
                    NotificationDelivery.attempts==0,NotificationDelivery.approved_at.is_(None),
                ).execution_options(synchronize_session=False))
            already = exists().where(NotificationDelivery.notification_id==Notification.id,NotificationDelivery.channel==channel)
            notifications = db.scalars(select(Notification).where(
                Notification.owner_id==preference.owner_id,
                Notification.created_at>=preference.created_at,
                ~already,
            ).order_by(Notification.created_at,Notification.id).limit(500)).all()
            for notification in notifications:
                row = NotificationDelivery(
                    owner_id=preference.owner_id,notification_id=notification.id,channel=channel,status="draft",
                    payload_encrypted=encrypt({"message":notification.message,"kind":notification.kind,
                        "destination":settings[destination],"settings_digest":settings_digest}),
                )
                try:
                    with db.begin_nested():
                        db.add(row)
                        db.flush()
                except IntegrityError:
                    continue
                count += 1
    return count


class _Rejected(Exception):
    pass


class _Uncertain(Exception):
    pass


def _send_email(payload):
    config = _smtp_config()
    if config is None:
        raise _Rejected("Email provider is not configured with verified TLS")
    message = EmailMessage()
    message["Subject"] = "InternPilot opportunity update"
    message["From"], message["To"] = config["sender"],payload["destination"]
    message["Message-ID"] = make_msgid(domain=config["sender"].split("@",1)[1])
    message.set_content(payload["message"])
    context = ssl.create_default_context()
    server = None
    try:
        if config["port"]==465:
            server = smtplib.SMTP_SSL(config["host"],config["port"],timeout=20,context=context)
        else:
            server = smtplib.SMTP(config["host"],config["port"],timeout=20)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        if config["username"]:
            server.login(config["username"],config["password"])
        if server.send_message(message):
            raise _Rejected("Email provider refused the recipient")
        return str(message["Message-ID"])[:255]
    except (smtplib.SMTPAuthenticationError,smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused,smtplib.SMTPDataError,smtplib.SMTPConnectError,smtplib.SMTPNotSupportedError,ssl.SSLCertVerificationError):
        raise _Rejected("Email provider rejected the request or TLS configuration") from None
    except (TimeoutError,OSError,smtplib.SMTPException):
        raise _Uncertain("Email provider outcome could not be confirmed; do not resend automatically") from None
    finally:
        if server is not None:
            try:
                server.quit()
            except (OSError,smtplib.SMTPException):
                server.close()


def _provider_json(response):
    if response.status_code>=500:
        raise _Uncertain("Provider outcome could not be confirmed; do not resend automatically")
    if not 200<=response.status_code<300:
        raise _Rejected("Provider rejected the notification request")
    try:
        result = response.json()
    except (ValueError,TypeError):
        raise _Uncertain("Provider acceptance could not be confirmed; do not resend automatically") from None
    if not isinstance(result,dict):
        raise _Uncertain("Provider acceptance could not be confirmed; do not resend automatically")
    return result


def _send_http(channel,payload):
    try:
        if channel=="telegram":
            token = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
            response = httpx.post(f"https://api.telegram.org/bot{quote(token,safe=':')}/sendMessage",
                json={"chat_id":payload["destination"],"text":payload["message"],"disable_web_page_preview":True},
                timeout=20,follow_redirects=False)
            data = _provider_json(response)
            if data.get("ok") is False:
                raise _Rejected("Telegram rejected the notification request")
            result = data.get("result")
            if data.get("ok") is not True or not isinstance(result,dict) or "message_id" not in result:
                raise _Uncertain("Telegram acceptance could not be confirmed; do not resend automatically")
            return str(result["message_id"])[:255]
        account = os.getenv("TWILIO_ACCOUNT_SID","")
        sender = os.getenv("TWILIO_WHATSAPP_FROM","").removeprefix("whatsapp:")
        response = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{quote(account,safe='')}/Messages.json",
            data={"From":"whatsapp:"+sender,"To":"whatsapp:"+payload["destination"],"Body":payload["message"]},
            auth=(account,os.getenv("TWILIO_AUTH_TOKEN","")),timeout=20,follow_redirects=False)
        data = _provider_json(response)
        if data.get("status") in {"failed","undelivered","canceled"}:
            raise _Rejected("WhatsApp provider rejected the notification request")
        if not data.get("sid") or data.get("status") not in {"accepted","scheduled","queued","sending","sent","delivered","read"}:
            raise _Uncertain("WhatsApp acceptance could not be confirmed; do not resend automatically")
        return str(data["sid"])[:255]
    except httpx.HTTPError:
        # Error strings may contain bot tokens, auth details or destinations.
        raise _Uncertain("Provider connection outcome could not be confirmed; do not resend automatically") from None


def send_delivery(db, owner_id, delivery_id, consent=False):
    if db.get_bind().dialect.name=="sqlite":
        db.execute(update(NotificationDelivery).where(NotificationDelivery.id==delivery_id,
            NotificationDelivery.owner_id==owner_id).values(updated_at=NotificationDelivery.updated_at).execution_options(synchronize_session=False))
    row = db.scalar(select(NotificationDelivery).where(NotificationDelivery.id==delivery_id,
        NotificationDelivery.owner_id==owner_id).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404,"Notification delivery not found")
    if row.status=="sent":
        return delivery_view(row)
    if consent is not True:
        raise HTTPException(422,"Explicit approval is required for this notification delivery")
    if row.status!="draft":
        raise HTTPException(409,"This delivery has already been attempted; check its outcome before creating another")
    preference = db.scalar(select(NotificationSettings).where(NotificationSettings.owner_id==owner_id).with_for_update().execution_options(populate_existing=True))
    if preference is None or row.channel not in CHANNEL_DESTINATIONS:
        raise HTTPException(409,"Notification channel settings are unavailable")
    settings = validate_notification_settings(decrypt(preference.settings_encrypted))
    payload = decrypt(row.payload_encrypted)
    expected = _settings_digest(settings)
    if not isinstance(payload,dict) or not isinstance(payload.get("settings_digest"),str) or not hmac.compare_digest(payload["settings_digest"],expected):
        raise HTTPException(409,"Notification settings changed; review a newly prepared delivery")
    if not settings[row.channel+"_enabled"] or payload.get("destination")!=settings[CHANNEL_DESTINATIONS[row.channel]]:
        raise HTTPException(409,"Notification channel or destination has changed")
    if not delivery_config_status()[row.channel]:
        raise HTTPException(409,"Notification provider is not configured")
    instant = datetime.now(timezone.utc)
    deferred = quiet_until(settings,instant)
    if row.not_before:
        try:
            prior = datetime.fromisoformat(row.not_before)
            if prior.tzinfo is None:
                prior = prior.replace(tzinfo=timezone.utc)
        except (ValueError,TypeError):
            raise HTTPException(409,"Notification deferral must be reviewed") from None
        if prior>instant and (deferred is None or prior>deferred):
            deferred = prior
    if deferred is not None:
        row.not_before = deferred.isoformat()
        row.last_error = "Quiet hours are active; approve this delivery again after the displayed time"
        row.updated_at = now()
        db.commit()
        return delivery_view(row)
    row.status,row.approved_at,row.not_before = "sending",instant.isoformat(),None
    row.attempts += 1
    row.last_error,row.updated_at = None,now()
    # Commit before any provider interaction. A crash cannot return this row to
    # a sendable draft, even if acceptance happened just before the crash.
    db.commit()
    try:
        provider_id = _send_email(payload) if row.channel=="email" else _send_http(row.channel,payload)
        status,error = "sent",None
    except _Rejected as exc:
        provider_id,status,error = None,"failed",str(exc)
    except _Uncertain as exc:
        provider_id,status,error = None,"uncertain",str(exc)
    except Exception:
        provider_id,status,error = None,"uncertain","Provider outcome could not be confirmed; do not resend automatically"
    db.refresh(row,with_for_update=True)
    row.status,row.provider_id,row.last_error,row.updated_at = status,provider_id,error,now()
    event(db,owner_id,"notification_"+status,f"{row.channel.title()} notification "+("accepted by provider" if status=="sent" else status))
    db.commit()
    return delivery_view(row)
