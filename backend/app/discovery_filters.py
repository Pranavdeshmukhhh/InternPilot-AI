"""Filters expose only disclosed facts; unknown values do not pass strict filters."""
import json
import re
from typing import Literal

from pydantic import Field

from .schemas import StrictModel


class DiscoveryCriteria(StrictModel):
    skills: str = Field(default="",max_length=500)
    degree_level: Literal["","undergraduate","masters","phd"] = ""
    graduation_year: int | None = Field(default=None,ge=2020,le=2050)
    duration_min: int = Field(default=0,ge=0,le=24)
    stipend_min: int = Field(default=0,ge=0,le=1000000)


def disclosed_details(job):
    description = str(job.get("description") or "")
    duration = re.search(r"\b(?:duration|internship|program(?:me)?)\s*(?:of|is|:|-|for|lasts|lasting)?\s*(\d{1,2})(?:\s*[-–—]\s*(\d{1,2}))?\s*months?\b",description,re.I)
    if duration is None:
        duration = re.search(r"\b(\d{1,2})(?:\s*[-–—]\s*(\d{1,2}))?[- ]months?\s+(?:internship|program(?:me)?)\b",description,re.I)
    months = int(duration[1]) if duration and 1<=int(duration[1])<=24 else None
    pay = job.get("compensation")
    minimum = None
    if isinstance(pay,str) and not re.search(r"\bunpaid\b|\bno (?:stipend|pay)\b",pay,re.I):
        amount = r"\d[\d,]*(?:\.\d+)?"
        match = re.search(rf"(?:₹|\bINR\b|\bRs\.?)[ ]*({amount})(?:\s*[-–—]\s*({amount}))?.{{0,20}}(?:per\s+month|/\s*month|monthly)",pay,re.I)
        if match:
            minimum = float(match[1].replace(",",""))
        else:
            try:
                structured = json.loads(pay)
            except ValueError:
                structured = None
            if isinstance(structured,dict) and structured.get("currency")=="INR" and str(structured.get("interval","")).lower() in {"month","monthly"}:
                value = structured.get("min")
                if isinstance(value,(int,float)) and not isinstance(value,bool) and 0<=value<=10000000:
                    minimum = value
    return {"duration_min_months":months,"monthly_stipend_min_inr":minimum,
            "note":"Only explicit month durations and disclosed monthly INR compensation are filterable; missing facts stay unknown."}


def matches(job,criteria):
    required = {value.strip().casefold() for value in criteria.skills.split(",") if value.strip()}
    if required and not required.issubset({str(value).casefold() for value in job.get("skills",[])}):
        return False
    req = job.get("requirements") or {}
    if criteria.degree_level and criteria.degree_level not in (req.get("degree_levels") or []):
        return False
    if criteria.graduation_year:
        year = criteria.graduation_year
        constraints = req.get("graduation_constraints") or [{"years":req.get("graduation_years"),"min":req.get("graduation_min"),"max":req.get("graduation_max")}]
        if year in (req.get("excluded_graduation_years") or []) or not any(clause.get("years") or clause.get("min") is not None or clause.get("max") is not None for clause in constraints):
            return False
        if any(clause.get("years") and year not in clause["years"] or clause.get("min") is not None and year<clause["min"] or clause.get("max") is not None and year>clause["max"] for clause in constraints):
            return False
    details = job.get("disclosed_details") or disclosed_details(job)
    if criteria.duration_min and (details["duration_min_months"] is None or details["duration_min_months"]<criteria.duration_min):
        return False
    if criteria.stipend_min and (details["monthly_stipend_min_inr"] is None or details["monthly_stipend_min_inr"]<criteria.stipend_min):
        return False
    return True
