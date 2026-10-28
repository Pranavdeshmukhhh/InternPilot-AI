"""Strict, bounded inputs for contacts, specific message approval and sender policy."""
import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from .schemas import StrictModel


class ContactInput(StrictModel):
    name: str = Field(min_length=1,max_length=120)
    email: str = Field(min_length=5,max_length=254)
    company: str = Field(min_length=1,max_length=200)
    source_url: str = Field(min_length=8,max_length=1500)
    employer_fact: str = Field(default="",max_length=500)
    role: str = Field(default="Software engineering internship",max_length=200)
    verified: Literal[True]

    @field_validator("email")
    @classmethod
    def email_valid(cls,value):
        value = value.strip().casefold()
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",value):
            raise ValueError("A valid recruiter address is required")
        return value

    @field_validator("name","company","role")
    @classmethod
    def no_headers(cls,value):
        if "\r" in value or "\n" in value or not value.strip():
            raise ValueError("Use a single nonempty line")
        return value.strip()

    @field_validator("source_url")
    @classmethod
    def source_link(cls,value):
        url = urlsplit(value)
        if url.scheme!="https" or not url.hostname or url.username or url.password:
            raise ValueError("Provide the HTTPS source where this contact was verified")
        return value


class SenderSettings(StrictModel):
    enabled: bool = False
    daily_limit: int = Field(default=35,ge=1,le=40)
    gap_minutes: int = Field(default=15,ge=10,le=1440)
    timezone: str = Field(default="Asia/Kolkata",max_length=100)
    start_hour: int = Field(default=9,ge=0,le=23)
    end_hour: int = Field(default=19,ge=1,le=24)
    weekdays_only: bool = True
    tone: Literal["concise","friendly","formal"] = "concise"
    signature: str = Field(default="",max_length=1000)
    subject_template: str = Field(default="",max_length=200)
    body_template: str = Field(default="",max_length=5000)
    followup_days: int = Field(default=7,ge=3,le=30)

    @model_validator(mode="after")
    def valid_window(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError,ValueError):
            raise ValueError("Choose a valid IANA timezone") from None
        if self.start_hour>=self.end_hour:
            raise ValueError("Sending window must end after it starts")
        if "\n" in self.subject_template or "\r" in self.subject_template:
            raise ValueError("Subjects must fit on one line")
        return self


class DraftInput(StrictModel):
    contact_id: str = Field(min_length=1,max_length=36)
    parent_id: str | None = Field(default=None,max_length=36)


class MessageEdit(StrictModel):
    subject: str = Field(min_length=1,max_length=200)
    body: str = Field(min_length=1,max_length=6000)
    facts_verified: Literal[True]

    @field_validator("subject")
    @classmethod
    def subject_line(cls,value):
        if "\r" in value or "\n" in value:
            raise ValueError("Subject must be a single line")
        return value.strip()


class MessageApproval(StrictModel):
    consent: Literal[True]
    preview_digest: str = Field(min_length=64,max_length=64)
    scheduled_at: str | None = Field(default=None,max_length=40)

    @field_validator("scheduled_at")
    @classmethod
    def aware_schedule(cls,value):
        if value:
            parsed = datetime.fromisoformat(value.replace("Z","+00:00"))
            if not parsed.tzinfo:
                raise ValueError("Scheduled time must include a timezone")
        return value
