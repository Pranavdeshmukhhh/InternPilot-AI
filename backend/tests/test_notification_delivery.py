"""Explicit notification delivery with isolated persistence and fake providers.

Every SMTP/HTTP boundary is replaced; these tests cannot send real messages.
"""
from datetime import datetime, timedelta, timezone
import json
import smtplib
import socket
from types import SimpleNamespace

from fastapi import HTTPException
import httpx
import pytest
from sqlalchemy import func, select

from app import notification_delivery as delivery
from app.models import Notification, NotificationDelivery, NotificationSettings
from app.security import decrypt, encrypt
from test_service_guards import isolated_services  # noqa: F401 -- pytest fixture registration


EMAIL = "synthetic-recipient@example.invalid"
MESSAGE = "Synthetic private opportunity notice 2050"
PROVIDER_SECRET = "synthetic-provider-credential-never-persist-2050"
PREFERENCE_CREATED = "2026-01-01T00:00:00+00:00"
NOTICE_CREATED = "2026-01-02T00:00:00+00:00"


@pytest.fixture
def outbox(isolated_services, monkeypatch):
    owner, _ = isolated_services.add_account("notification-owner")
    other, _ = isolated_services.add_account("notification-other")
    for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_STARTTLS", "SMTP_FROM",
                 "TELEGRAM_BOT_TOKEN", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM"):
        monkeypatch.delenv(name, raising=False)

    def blocked_connect(*args, **kwargs):
        raise AssertionError("Notification tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    calls, behavior = [], {}

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self, *args, **kwargs):
            return 250, b"Synthetic SMTP"

        def starttls(self, *args, **kwargs):
            return 220, b"Synthetic TLS"

        def login(self, *args, **kwargs):
            return 235, b"Synthetic authenticated"

        def send_message(self, message, *args, **kwargs):
            calls.append({"channel": "email", "message": message})
            if behavior.get("before"):
                behavior["before"]()
            if behavior.get("error"):
                raise behavior["error"]
            return {}

        def quit(self):
            if behavior.get("quit_error"):
                raise behavior["quit_error"]
            return 221, b"Synthetic goodbye"

        def close(self):
            behavior["closed"] = True

    def post(url, **kwargs):
        channel = "telegram" if "api.telegram.org" in url else "whatsapp"
        calls.append({"channel": channel, "url": url, "kwargs": kwargs})
        if behavior.get("before"):
            behavior["before"]()
        if behavior.get("error"):
            raise behavior["error"]
        code = behavior.get("status", 200 if channel == "telegram" else 201)
        body = behavior.get("body", {"ok": True, "result": {"message_id": 2050}} if channel == "telegram" else {"sid": "SMsynthetic-provider-id", "status": "queued"})
        return httpx.Response(code, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTP)
    monkeypatch.setattr(httpx, "post", post)
    return SimpleNamespace(sessions=isolated_services.sessions, owner=owner, other=other,
                           calls=calls, behavior=behavior, monkeypatch=monkeypatch)


def configure_provider(outbox, channel):
    variables = {
        "email": {"SMTP_HOST": "smtp.example.invalid", "SMTP_PORT": "587", "SMTP_STARTTLS": "true",
                  "SMTP_USER": "synthetic-smtp-user", "SMTP_PASSWORD": PROVIDER_SECRET,
                  "SMTP_FROM": "synthetic-sender@example.invalid"},
        "telegram": {"TELEGRAM_BOT_TOKEN": PROVIDER_SECRET},
        "whatsapp": {"TWILIO_ACCOUNT_SID": "ACsynthetic-account", "TWILIO_AUTH_TOKEN": PROVIDER_SECRET,
                     "TWILIO_WHATSAPP_FROM": "whatsapp:+15005550006"},
    }
    for key, value in variables[channel].items():
        outbox.monkeypatch.setenv(key, value)


def preferences(outbox, *, owner=None, **changes):
    owner = owner or outbox.owner
    normalized = delivery.validate_notification_settings(changes)
    with outbox.sessions() as db:
        row = db.get(NotificationSettings, owner)
        if row is None:
            row = NotificationSettings(owner_id=owner, settings_encrypted=encrypt(normalized),
                                       created_at=PREFERENCE_CREATED, updated_at=PREFERENCE_CREATED)
            db.add(row)
        else:
            row.settings_encrypted = encrypt(normalized)
            row.updated_at = NOTICE_CREATED
        db.commit()
    return normalized


def notice(outbox, *, owner=None, created_at=NOTICE_CREATED, message=MESSAGE):
    with outbox.sessions() as db:
        row = Notification(owner_id=owner or outbox.owner, kind="opportunity", message=message, created_at=created_at)
        db.add(row)
        db.commit()
        return row.id


def materialize(outbox, owner=None):
    with outbox.sessions() as db:
        count = delivery.materialize_delivery_drafts(db, owner_id=owner)
        db.commit()
        return count


def test_abandoned_send_checkpoint_becomes_uncertain_without_resending(outbox):
    delivery_id = draft(outbox)
    with outbox.sessions() as db:
        row = db.get(NotificationDelivery,delivery_id)
        row.status,row.attempts,row.approved_at,row.updated_at = "sending",1,NOTICE_CREATED,NOTICE_CREATED
        db.commit()
    assert materialize(outbox,outbox.other) == 0
    with outbox.sessions() as db:
        assert db.get(NotificationDelivery,delivery_id).status == "sending"
    assert materialize(outbox,outbox.owner) == 0
    with outbox.sessions() as db:
        row = db.get(NotificationDelivery,delivery_id)
        assert row.status == "uncertain" and row.attempts == 1
        with pytest.raises(HTTPException) as attempted:
            delivery.send_delivery(db,outbox.owner,delivery_id,consent=True)
        assert attempted.value.status_code == 409
    assert outbox.calls == []


def draft(outbox, channel="email", **changes):
    configure_provider(outbox, channel)
    destination = {"email": {"email_to": EMAIL}, "telegram": {"telegram_chat_id": "123456789"},
                   "whatsapp": {"whatsapp_to": "+15005550007"}}[channel]
    preferences(outbox, **{f"{channel}_enabled": True, **destination, **changes})
    notification_id = notice(outbox)
    assert materialize(outbox, outbox.owner) == 1
    with outbox.sessions() as db:
        row = db.scalar(select(NotificationDelivery).where(NotificationDelivery.notification_id == notification_id))
        return row.id


def send(outbox, delivery_id, *, owner=None, consent=True):
    with outbox.sessions() as db:
        result = delivery.send_delivery(db, owner or outbox.owner, delivery_id, consent=consent)
        db.commit()
        return result


def test_notification_destinations_and_quiet_hours_are_strictly_validated():
    settings = delivery.validate_notification_settings({})
    assert settings["email_enabled"] is False
    assert settings["telegram_enabled"] is False
    assert settings["whatsapp_enabled"] is False
    for invalid in ({"email_enabled": "true"}, {"telegram_enabled": 1}, {"whatsapp_enabled": None},
                    {"unknown_provider": True}, {"email_enabled": True, "email_to": "bad-address"},
                    {"email_to": "candidate@example.invalid\r\nBcc: attacker@example.invalid"},
                    {"telegram_enabled": True, "telegram_chat_id": "not-a-chat-id"},
                    {"whatsapp_enabled": True, "whatsapp_to": "123"},
                    {"quiet_hours_enabled": True, "quiet_start": "25:70", "quiet_end": "08:00", "timezone": "UTC"},
                    {"quiet_hours_enabled": True, "quiet_start": "22:00", "quiet_end": "08:00", "timezone": "Invalid/Timezone"}):
        with pytest.raises((HTTPException, ValueError)):
            delivery.validate_notification_settings(invalid)


def test_drafts_are_opted_in_configured_owned_new_and_deduplicated(outbox):
    configure_provider(outbox, "email")
    preferences(outbox, email_enabled=True, email_to=EMAIL)
    preferences(outbox, owner=outbox.other, email_enabled=True, email_to="other@example.invalid")
    old = notice(outbox, created_at="2025-12-31T23:59:59+00:00")
    current = notice(outbox)
    other = notice(outbox, owner=outbox.other)
    assert materialize(outbox, outbox.owner) == 1
    assert materialize(outbox, outbox.owner) == 0
    assert outbox.calls == []
    with outbox.sessions() as db:
        rows = list(db.scalars(select(NotificationDelivery)))
        assert len(rows) == 1
        row = rows[0]
        assert row.owner_id == outbox.owner and row.notification_id == current
        assert row.notification_id not in {old, other}
        assert row.status == "draft" and row.attempts == 0 and row.approved_at is None
        assert MESSAGE.encode() not in row.payload_encrypted
        assert EMAIL.encode() not in row.payload_encrypted
        payload = decrypt(row.payload_encrypted)
        assert payload["message"] == MESSAGE and payload["destination"] == EMAIL
        assert payload["settings_digest"]
        assert PROVIDER_SECRET not in json.dumps(payload)
        assert PROVIDER_SECRET not in json.dumps(delivery.delivery_view(row))


def test_disabled_or_unconfigured_channels_never_make_delivery_drafts(outbox):
    assert delivery.delivery_config_status() == {"browser": True, "email": False, "telegram": False, "whatsapp": False}
    preferences(outbox, email_enabled=True, email_to=EMAIL)
    notice(outbox)
    assert materialize(outbox) == 0
    configure_provider(outbox, "email")
    assert delivery.delivery_config_status()["email"] is True
    assert PROVIDER_SECRET not in json.dumps(delivery.delivery_config_status())
    outbox.monkeypatch.setenv("SMTP_STARTTLS", "false")
    assert delivery.delivery_config_status()["email"] is False
    outbox.monkeypatch.setenv("SMTP_PORT", "465")
    assert delivery.delivery_config_status()["email"] is True
    assert PROVIDER_SECRET not in json.dumps(delivery.delivery_config_status())
    preferences(outbox, email_enabled=False, email_to=EMAIL)
    assert materialize(outbox) == 0
    assert outbox.calls == []


@pytest.mark.parametrize("channel", ["email", "telegram", "whatsapp"])
def test_explicit_consent_checkpoints_before_provider_and_sent_is_idempotent(outbox, channel):
    delivery_id = draft(outbox, channel)
    with pytest.raises(HTTPException) as scoped:
        send(outbox, delivery_id, owner=outbox.other)
    assert scoped.value.status_code == 404
    with pytest.raises(HTTPException) as unapproved:
        send(outbox, delivery_id, consent=False)
    assert unapproved.value.status_code == 422
    assert outbox.calls == []

    def committed_checkpoint():
        with outbox.sessions() as observer:
            persisted = observer.get(NotificationDelivery, delivery_id)
            assert persisted.status == "sending"
            assert persisted.approved_at is not None
            assert persisted.attempts == 1

    outbox.behavior["before"] = committed_checkpoint
    result = send(outbox, delivery_id)
    assert result["status"] == "sent"
    assert len(outbox.calls) == 1 and outbox.calls[0]["channel"] == channel
    assert PROVIDER_SECRET not in json.dumps(result)
    if channel != "email":
        assert outbox.calls[0]["kwargs"]["follow_redirects"] is False
        assert outbox.calls[0]["kwargs"]["timeout"]
    assert send(outbox, delivery_id)["status"] == "sent"
    assert materialize(outbox, outbox.owner) == 0
    assert len(outbox.calls) == 1
    with outbox.sessions() as db:
        row = db.get(NotificationDelivery, delivery_id)
        assert row.status == "sent" and row.attempts == 1
        assert PROVIDER_SECRET not in json.dumps(decrypt(row.payload_encrypted))
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 1


def test_provider_timeout_is_uncertain_and_never_automatically_retried(outbox):
    delivery_id = draft(outbox, "telegram")
    outbox.behavior["error"] = httpx.ReadTimeout(f"Provider request included {PROVIDER_SECRET}")
    result = send(outbox, delivery_id)
    assert result["status"] == "uncertain"
    assert PROVIDER_SECRET not in json.dumps(result)
    with pytest.raises(HTTPException) as retry:
        send(outbox, delivery_id)
    assert retry.value.status_code == 409
    assert materialize(outbox, outbox.owner) == 0
    assert len(outbox.calls) == 1
    with outbox.sessions() as db:
        row = db.get(NotificationDelivery, delivery_id)
        assert row.status == "uncertain" and row.attempts == 1
        assert PROVIDER_SECRET not in (row.last_error or "")


def test_provider_rejection_is_failed_without_exposing_response_or_retrying(outbox):
    delivery_id = draft(outbox, "whatsapp")
    outbox.behavior.update(status=403, body={"message": f"Rejected secret {PROVIDER_SECRET}"})
    result = send(outbox, delivery_id)
    assert result["status"] == "failed"
    assert PROVIDER_SECRET not in json.dumps(result)
    with pytest.raises(HTTPException) as retry:
        send(outbox, delivery_id)
    assert retry.value.status_code == 409
    assert len(outbox.calls) == 1
    with outbox.sessions() as db:
        row = db.get(NotificationDelivery, delivery_id)
        assert row.attempts == 1 and PROVIDER_SECRET not in (row.last_error or "")


def test_changed_destination_or_missing_configuration_blocks_existing_draft(outbox):
    delivery_id = draft(outbox)
    preferences(outbox, email_enabled=True, email_to="changed@example.invalid")
    with pytest.raises(HTTPException) as stale:
        send(outbox, delivery_id)
    assert stale.value.status_code == 409
    preferences(outbox, email_enabled=True, email_to=EMAIL)
    outbox.monkeypatch.delenv("SMTP_HOST")
    with pytest.raises(HTTPException) as unconfigured:
        send(outbox, delivery_id)
    assert unconfigured.value.status_code == 409
    assert outbox.calls == []
    with outbox.sessions() as db:
        row = db.get(NotificationDelivery, delivery_id)
        assert row.status == "draft" and row.attempts == 0
        assert decrypt(row.payload_encrypted)["destination"] == EMAIL


def test_stale_unattempted_draft_is_rebuilt_for_review_at_new_destination(outbox):
    old_id = draft(outbox)
    new_destination = "changed@example.invalid"
    with outbox.sessions() as db:
        notification_id = db.get(NotificationDelivery, old_id).notification_id
    preferences(outbox, email_enabled=True, email_to=new_destination)
    with pytest.raises(HTTPException) as stale:
        send(outbox, old_id)
    assert stale.value.status_code == 409
    assert materialize(outbox, outbox.owner) == 1
    with outbox.sessions() as db:
        assert db.get(NotificationDelivery, old_id) is None
        fresh = db.scalar(select(NotificationDelivery).where(NotificationDelivery.notification_id == notification_id))
        assert fresh.id != old_id
        assert fresh.status == "draft" and fresh.attempts == 0 and fresh.approved_at is None
        assert decrypt(fresh.payload_encrypted)["destination"] == new_destination
        fresh_id = fresh.id
    with pytest.raises(HTTPException) as removed:
        send(outbox, old_id)
    assert removed.value.status_code == 404
    with pytest.raises(HTTPException) as unapproved:
        send(outbox, fresh_id, consent=False)
    assert unapproved.value.status_code == 422
    assert outbox.calls == []
    result = send(outbox, fresh_id, consent=True)
    assert result["status"] == "sent" and result["destination"] == new_destination
    assert len(outbox.calls) == 1
    assert outbox.calls[0]["message"]["To"] == new_destination


@pytest.mark.parametrize("outcome", ["sent", "failed", "uncertain"])
def test_materialization_never_rebuilds_attempted_delivery_after_settings_change(outbox, outcome):
    original_id = draft(outbox)
    if outcome == "failed":
        outbox.behavior["error"] = smtplib.SMTPRecipientsRefused({EMAIL: (550, b"Synthetic recipient refusal")})
    elif outcome == "uncertain":
        outbox.behavior["error"] = TimeoutError("Synthetic provider timeout")
    assert send(outbox, original_id)["status"] == outcome
    preferences(outbox, email_enabled=True, email_to="changed@example.invalid")
    assert materialize(outbox, outbox.owner) == 0
    with outbox.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 1
        retained = db.get(NotificationDelivery, original_id)
        assert retained.status == outcome and retained.attempts == 1
        assert decrypt(retained.payload_encrypted)["destination"] == EMAIL
    assert len(outbox.calls) == 1


def test_smtp_disconnect_timeout_after_acceptance_does_not_erase_sent_outcome(outbox):
    delivery_id = draft(outbox)
    outbox.behavior["quit_error"] = TimeoutError("Synthetic SMTP disconnect timeout")
    assert send(outbox, delivery_id)["status"] == "sent"
    assert outbox.behavior["closed"] is True
    assert len(outbox.calls) == 1


def test_quiet_hours_handle_overnight_timezone_and_exact_end_boundary():
    settings = delivery.validate_notification_settings({"quiet_hours_enabled": True, "quiet_start": "22:00", "quiet_end": "08:00", "timezone": "Asia/Kolkata"})
    # 23:30 local on January 2 is 18:00 UTC; release at 08:00 local January 3.
    instant = datetime(2026, 1, 2, 18, 0, tzinfo=timezone.utc)
    until = delivery.quiet_until(settings, at=instant)
    assert until is not None and until.tzinfo is not None
    assert until.astimezone(timezone.utc) == datetime(2026, 1, 3, 2, 30, tzinfo=timezone.utc)
    assert delivery.quiet_until(settings, at=until) is None
    assert delivery.quiet_until({**settings, "quiet_hours_enabled": False}, at=instant) is None


def test_quiet_draft_is_deferred_without_starting_provider_or_automatic_send(outbox, monkeypatch):
    delivery_id = draft(outbox)
    deferred_until = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(delivery, "quiet_until", lambda settings, at=None: deferred_until)
    result = send(outbox, delivery_id)
    assert result["status"] == "draft" and result["not_before"]
    assert outbox.calls == []
    assert materialize(outbox, outbox.owner) == 0
    with outbox.sessions() as db:
        row = db.get(NotificationDelivery, delivery_id)
        assert row.status == "draft" and row.attempts == 0
        assert datetime.fromisoformat(row.not_before) == deferred_until
