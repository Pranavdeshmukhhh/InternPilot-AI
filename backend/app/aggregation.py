"""Read-only interoperability with JobSpy exports and InternScan public feeds.

This independently implemented boundary consumes documented record formats. It
does not run upstream scrapers, bypass access rules, or copy their source code.
Imported references never become employer-verified by virtue of aggregation.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from . import discovery as safe
from .matching import extract_requirements, plain_text

MAX_RECORDS = 2000
MAX_IMPORT_BYTES = 8 * 1024 * 1024


def _text(value, limit=100000):
    return value.strip()[:limit] if isinstance(value,str) else ""


def _instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _public_https(value):
    try:
        safe._syntax_url(value)
        parts = urlsplit(value)
        if parts.scheme != "https" or parts.username or parts.password or parts.hostname in {"localhost", "localhost.localdomain"}:
            return None
        try:
            if not ipaddress.ip_address(parts.hostname).is_global:
                return None
        except ValueError:
            pass
        return safe.canonical_url(value)
    except (ValueError, TypeError, safe.DiscoveryError):
        return None


def _number(value):
    try:
        result = float(value)
        return result if not isinstance(value,bool) and math.isfinite(result) and result >= 0 else None
    except (ValueError,TypeError,OverflowError):
        return None


def _location(value):
    if isinstance(value,list):
        return "; ".join(_text(item,200) for item in value if isinstance(item,str))[:1000]
    if isinstance(value,dict):
        return ", ".join(_text(value.get(key),100) for key in ("city","state","country") if value.get(key))
    return _text(value,1000)


def normalize_record(record, provider):
    if not isinstance(record,dict):
        return None
    title = _text(record.get("title"),500)
    if not safe.INTERNSHIP.search(title):
        return None
    url = _public_https(record.get("job_url_direct") or record.get("job_url") or record.get("url") or "")
    company = _text(record.get("company"),300)
    if not url or not company:
        return None
    description = plain_text(_text(record.get("description")))
    location = _location(record.get("locations") or record.get("location"))
    remote_value = record.get("is_remote",record.get("remote"))
    remote = True if remote_value is True or str(remote_value).casefold() in {"true","1","yes"} else False if remote_value is False or str(remote_value).casefold() in {"false","0","no"} else None
    compensation = _text(record.get("compensation"),500) or None
    low,high = _number(record.get("min_amount")),_number(record.get("max_amount"))
    currency = _text(record.get("currency"),10)
    if compensation is None and currency and (low is not None or high is not None):
        amounts = [f"{number:g}" for number in (low,high) if number is not None]
        compensation = currency+" "+"–".join(dict.fromkeys(amounts))
        if record.get("interval"):
            compensation += " / "+_text(record["interval"],40)
    deadline_value = record.get("deadline") or record.get("application_deadline")
    active = record.get("active") is not False and str(record.get("status","")).lower() not in {"closed","expired","removed"}
    requirements = extract_requirements(description,location=location,title=title)
    return {"external_id":_text(record.get("id") or record.get("uid") or url,1000),
            "opportunity_type":"internship","title":title,"company":company,"url":url,
            "description":description,"location":location or "Not specified","remote":remote,
            "remote_status":"remote" if remote is True else "on_site" if remote is False else "unknown",
            "skills":requirements["skills"],"requirements":requirements,"active":active,
            "published_at":_instant(record.get("date_posted") or record.get("posted")),
            "published_date":_text(record.get("date_posted") or record.get("posted"),40) or None,
            "deadline":_instant(deadline_value),"deadline_raw":_text(deadline_value,100) or None,
            "compensation":compensation,"source":provider,"aggregator_site":_text(record.get("site"),100) or None,
            "provider_first_seen":_text(record.get("first_seen"),100) or None,
            "provider_last_seen":_text(record.get("last_seen"),100) or None,
            "application_url_verified":False,"verification_status":"unverified",
            "verification_note":"Aggregator reference only. Verify the employer page and eligibility before applying."}


def records_from_bytes(content, filename):
    if len(content)>MAX_IMPORT_BYTES:
        raise ValueError("Opportunity imports are limited to 8 MiB")
    try:
        text = content.decode("utf-8-sig")
        if filename.lower().endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(text)))
        elif filename.lower().endswith(".jsonl"):
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif filename.lower().endswith(".json"):
            data = json.loads(text)
            rows = data if isinstance(data,list) else data.get("jobs",data.get("data",[])) if isinstance(data,dict) else None
        else:
            raise ValueError("Use a JobSpy CSV/JSON/JSONL export or an InternScan JSON feed")
    except (UnicodeError,json.JSONDecodeError,csv.Error):
        raise ValueError("The import is not valid UTF-8 CSV or JSON") from None
    if not isinstance(rows,list) or len(rows)>MAX_RECORDS:
        raise ValueError("An import must contain a list of at most 2,000 opportunity records")
    return rows


async def discover_aggregation(source, cache=None):
    if source.get("permitted") is not True:
        raise safe.DiscoveryError("Confirm authorized read-only access before enabling this feed")
    kind = source.get("kind")
    url = source.get("url") or ("https://internscan.vercel.app/in/api/active.json" if kind=="internscan" else "")
    safe._syntax_url(url)
    if kind=="internscan" and (urlsplit(url).hostname!="internscan.vercel.app" or not urlsplit(url).path.endswith("/api/active.json")):
        raise safe.DiscoveryError("InternScan uses its published country/global active JSON feed")
    cache = dict(cache or {})
    headers = {"User-Agent":safe.USER_AGENT,"Accept":"application/json,text/csv"}
    if cache.get("etag"): headers["If-None-Match"] = cache["etag"]
    if cache.get("last_modified"): headers["If-Modified-Since"] = cache["last_modified"]
    async with httpx.AsyncClient(timeout=30,follow_redirects=False,trust_env=True) as client:
        response = await safe._request(client,url,headers=headers,robots=True)
    next_cache = {**cache,"etag":response.headers.get("etag"),"last_modified":response.headers.get("last-modified")}
    if response.status_code==304:
        return {"jobs":[],"cache":next_cache,"not_modified":True}
    filename = "export.csv" if "csv" in response.headers.get("content-type","") or urlsplit(url).path.endswith(".csv") else "export.jsonl" if urlsplit(url).path.endswith(".jsonl") else "export.json"
    try:
        rows = records_from_bytes(response.content,filename)
    except ValueError as exc:
        raise safe.DiscoveryError(str(exc)) from None
    jobs = [normalized for row in rows if (normalized:=normalize_record(row,kind))]
    for job in jobs:
        job["source_url"] = url
    # A third-party feed is not an authoritative complete employer inventory.
    return {"jobs":jobs,"cache":{**next_cache,"truncated":True,"reference_feed":True,"records_seen":len(rows)},"not_modified":False}
