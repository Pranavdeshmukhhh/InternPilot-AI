"""Typed, candidate-independent projections. Unknown facts stay unknown."""
from datetime import datetime, timezone
import hashlib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

VERSION = 1


def instant(value):
    if not value:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def projection(data, discovered):
    kind = data.get("opportunity_type", "internship")
    deadline = instant(data.get("deadline"))
    parts = urlsplit(str(data.get("url") or ""))
    params = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in {"source", "ref", "gh_src", "lever-source"} and not k.lower().startswith("utm_")]
    canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(sorted(params)), ""))
    return {
        "projection_version": VERSION, "kind": kind,
        "authority_rank":1 if data.get("verification_status") == "official_metadata_verified" else 0 if data.get("source") in {"internscan", "jobspy_feed", "jobspy", "github_list", "search"} or data.get("verification_status") in {"unverified", "reference_only"} else 2,
        "company_key": str(data.get("company", "")).casefold(),
        "location_key": str(data.get("location", "")).casefold(),
        "url_key":hashlib.sha256(canonical.encode()).hexdigest() if canonical else None,
        "search_document": " ".join(str(data.get(k, "")) for k in ("title", "company", "description", "location")).casefold(),
        "remote_flag": data.get("remote") is True, "active_flag": data.get("active") is not False,
        "deadline_at": deadline,
        "expires_at": deadline or (instant(data.get("ends_at")) if kind == "hackathon" else None),
        "sort_at": instant(data.get("published_at")) or instant(discovered),
    }
