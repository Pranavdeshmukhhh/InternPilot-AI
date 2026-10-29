import re
from datetime import date
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .config import settings


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    otp: str = Field(default="", max_length=8)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("A valid email address is required")
        return value


class RegistrationCredentials(Credentials):
    registration_token: str = Field(default="", max_length=256)


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)
    otp: str = Field(default="", max_length=8)


class Profile(StrictModel):
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=80)
    country: str = Field(default="India", max_length=100)
    graduation_year: int = Field(default=2029, ge=2020, le=2050)
    degree: str = Field(default="", max_length=200)
    university: str = Field(default="", max_length=250)
    skills: list[str] = Field(default_factory=list, max_length=100)
    interests: list[str] = Field(default_factory=lambda:["Software engineering", "AI/ML", "Cloud computing", "Web development"], max_length=100)
    github: str = Field(default="", max_length=500)
    linkedin: str = Field(default="", max_length=500)
    portfolio: str = Field(default="", max_length=500)
    projects: list[dict] = Field(default_factory=list, max_length=40)
    experience: list[dict] = Field(default_factory=list, max_length=40)
    experience_years: float | None = Field(default=None, ge=0, le=80)
    verified_fields: list[str] = Field(default_factory=lambda:["country", "graduation_year"], max_length=50)
    preferred_employers: list[str] = Field(default_factory=lambda:["Microsoft", "Google", "Amazon", "NVIDIA", "Adobe", "Atlassian", "Salesforce"], max_length=100)
    preferred_locations: list[str] = Field(default_factory=lambda:["India", "Remote"], max_length=100)
    preferred_local_cities: list[str] = Field(default_factory=lambda:["Nagpur", "Pune"], max_length=20)
    include_nearby_locations: bool = True
    remote_preferred: bool = True
    paid_preferred: bool = True
    work_authorization: list[str] = Field(default_factory=list, max_length=30)
    verified_answers: dict[str, dict] = Field(default_factory=dict)
    preferred_roles: list[str] = Field(default_factory=lambda:["Software engineering", "AI/ML", "Data science", "Cloud engineering", "Cybersecurity", "Web development", "Research"], max_length=50)
    hackathon_interests: list[str] = Field(default_factory=lambda:["AI/ML", "Cloud", "Open innovation"], max_length=50)
    experience_level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    availability_start: str | None = Field(default=None, max_length=10)
    availability_end: str | None = Field(default=None, max_length=10)

    @field_validator("preferred_local_cities")
    @classmethod
    def valid_local_cities(cls, values):
        cities = []
        for value in values:
            value = value.strip()
            if len(value) > 100:
                raise ValueError("Local city names must be at most 100 characters")
            if value and value.casefold() not in {city.casefold() for city in cities}:
                cities.append(value)
        return cities

    @field_validator("github", "linkedin", "portfolio")
    @classmethod
    def public_links(cls, value):
        if value and (urlsplit(value).scheme != "https" or not urlsplit(value).hostname or urlsplit(value).username):
            raise ValueError("Portfolio links must use HTTPS")
        return value

    @model_validator(mode="after")
    def verified_known(self):
        allowed = set(type(self).model_fields) - {"verified_fields"}
        if not set(self.verified_fields).issubset(allowed):
            raise ValueError("Unknown field in verified_fields")
        for value in (self.availability_start, self.availability_end):
            if value:
                date.fromisoformat(value)
        if self.availability_start and self.availability_end and self.availability_end < self.availability_start:
            raise ValueError("Availability end must follow availability start")
        return self


class Policy(StrictModel):
    mode: Literal["discovery", "assisted", "auto"] = "discovery"
    auto_consent: bool = False
    allowed_companies: list[str] = Field(default_factory=list, max_length=100)
    allowed_origins: list[str] = Field(default_factory=list, max_length=100)
    minimum_score: int = Field(default=80, ge=0, le=100)
    daily_limit: int = Field(default=5, ge=1, le=50)
    emergency_stop: bool = False
    deadline_reminders: bool = True
    deadline_reminder_hours: int = Field(default=48, ge=1, le=168)
    deadline_minimum_score: int = Field(default=50, ge=0, le=100)
    auto_prepare: bool = False
    preparation_minimum_score: int = Field(default=70, ge=0, le=100)
    daily_preparation_limit: int = Field(default=10, ge=1, le=50)
    new_match_alerts: bool = True
    alert_minimum_score: int = Field(default=70, ge=0, le=100)

    @field_validator("allowed_origins")
    @classmethod
    def origins(cls, values):
        for value in values:
            parts = urlsplit(value)
            local_test = settings.test_mode and value == settings.test_portal_origin
            if not local_test and (parts.scheme != "https" or not parts.hostname):
                raise ValueError("Allowed application origins must use HTTPS")
            if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/") or "*" in value:
                raise ValueError("Supply exact application origins without paths or wildcards")
        return [v.rstrip("/") for v in values]

    @model_validator(mode="after")
    def explicit_auto(self):
        if self.mode == "auto" and (not self.auto_consent or not self.allowed_companies or not self.allowed_origins):
            raise ValueError("Auto Apply needs explicit consent, allowed employers, and exact allowed origins")
        return self


class SourceInput(StrictModel):
    kind: Literal["greenhouse", "lever", "ashby", "smartrecruiters", "feed", "html", "search", "workday", "mlh", "devpost", "github_list", "internscan", "jobspy_feed"]
    slug: str = Field(default="", max_length=200)
    company: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=1500)
    permitted: bool = False
    enabled: bool = True
    interval_seconds: int = Field(default=1800, ge=300, le=604800)

    @model_validator(mode="after")
    def source_access(self):
        if self.enabled and self.kind in {"feed","html","workday","jobspy_feed"} and not self.url:
            raise ValueError("An enabled feed or page source requires an authorized HTTPS URL")
        minimum = {"mlh":1800,"github_list":1800,"internscan":900,"jobspy_feed":900}.get(self.kind,300)
        if self.interval_seconds<minimum:
            raise ValueError(f"This source requires a refresh interval of at least {minimum} seconds")
        return self


class ApplyInput(StrictModel):
    opportunity_id: str


class GenerateInput(ApplyInput):
    kind: Literal["resume", "cover_letter"] = "resume"


class ConsentInput(StrictModel):
    consent: bool


class StopInput(StrictModel):
    stopped: bool


class StatusInput(StrictModel):
    status: Literal["assessment", "interview", "offer", "rejected", "withdrawn"]


class ReadInput(StrictModel):
    read: bool = True
