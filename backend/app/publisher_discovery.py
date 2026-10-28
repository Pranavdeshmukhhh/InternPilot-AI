"""Bounded publisher link discovery; suggestions are never crawl permission.

An incubator/company directory is useful even when it has no JobPosting schema.
Extract only links actually present in a page. Do not guess employers, board
slugs, contact addresses, location, eligibility or whether an employer is small.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


class PublisherLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[dict] = []
        self._link = None
        self._parts: list[str] = []
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self._hidden += 1
        if tag == "a" and attrs.get("href") and len(self.links) < 200:
            self._link = attrs["href"][:1500]
            self._parts = [attrs.get("aria-label", "")[:300], attrs.get("title", "")[:300]]
        elif tag == "link" and attrs.get("type", "").lower() in {"application/rss+xml", "application/atom+xml"} and len(self.links) < 200:
            self.links.append({"url": attrs.get("href", "")[:1500], "title": attrs.get("title", "Publisher feed")[:300], "feed": True})

    def handle_data(self, data):
        if self._link is not None and not self._hidden and len(self._parts) < 20:
            self._parts.append(data[:300])

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._hidden = max(0, self._hidden - 1)
        if tag == "a" and self._link is not None:
            self.links.append({"url": self._link, "title": " ".join(" ".join(self._parts).split())[:300]})
            self._link, self._parts = None, []


def source_candidate(url: str, title: str, evidence_url: str, *, feed=False) -> dict | None:
    # Lazy imports avoid a cycle with the connector entrypoint.
    from .discovery import DiscoveryError, _syntax_url, canonical_url
    if len(url) > 1500 or len(evidence_url) > 1500:
        return None
    try:
        _syntax_url(url)
        _syntax_url(evidence_url)
    except DiscoveryError:
        return None
    parsed = urlsplit(url)
    host = parsed.hostname.lower()
    parts = [part for part in parsed.path.split("/") if part]
    kind, slug, target = "html", "", canonical_url(url)
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        kind, slug = "greenhouse", parts[0]
    elif host == "boards-api.greenhouse.io" and len(parts) >= 4 and parts[:2] == ["v1", "boards"]:
        kind, slug = "greenhouse", parts[2]
    elif host in {"jobs.lever.co", "jobs.eu.lever.co"} and parts:
        # EU postings need a distinct regional API, not the US-only connector.
        if host != "jobs.lever.co":
            return None
        kind, slug = "lever", parts[0]
    elif host == "jobs.ashbyhq.com" and parts:
        kind, slug = "ashby", parts[0]
    elif host in {"jobs.smartrecruiters.com", "careers.smartrecruiters.com"} and parts:
        kind, slug = "smartrecruiters", parts[0]
    elif feed or parsed.path.lower().endswith((".rss", ".xml", "/feed", "/feed/", "/rss", "/atom")):
        kind = "feed"
    elif not re.search(r"(?:^|[/_-])(?:careers?|jobs?|internships?|opportunities|hackathons?|fellowships?|students?|research|programs?|placements?|recruitment)(?:$|[/_.-])", parsed.path, re.I):
        return None
    if kind not in {"html", "feed"}:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", slug):
            return None
        target = ""
    key = f"{kind}:{slug}:{target}"
    return {"id": hashlib.sha256(key.encode()).hexdigest()[:24], "kind": kind, "slug": slug,
            "url": target or None, "company": (title.strip() or slug or host)[:200],
            "evidence_url": canonical_url(evidence_url), "discovered_at": datetime.now(timezone.utc).isoformat(),
            "reason": "Linked public ATS board" if slug else "Publisher-linked feed" if kind == "feed" else "Publisher-linked opportunity page; supported metadata still needs checking",
            "verified": False}


def page_links(text: str, base_url: str) -> list[dict]:
    parser = PublisherLinks()
    parser.feed(text)
    result, seen = [], set()
    for link in parser.links:
        url = urljoin(base_url, link["url"])
        if url not in seen:
            result.append({**link, "url": url})
            seen.add(url)
    return result


def merge_candidates(previous: list, incoming: list, limit=40) -> list[dict]:
    # New suggestions first, preserving first discovery on repeated sightings.
    old = {item.get("id"): item for item in previous if isinstance(item, dict) and item.get("id")}
    merged = {}
    for item in [*incoming, *previous]:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if item["id"] not in merged:
            merged[item["id"]] = {**item, "discovered_at": old.get(item["id"], item).get("discovered_at")}
    return list(merged.values())[:limit]


def page_candidates(text: str, base_url: str) -> list[dict]:
    candidates = []
    current = source_candidate(base_url, "Publisher opportunity page", base_url)
    if current:
        candidates.append(current)
    for link in page_links(text, base_url):
        candidate = source_candidate(link["url"], link["title"], base_url, feed=link.get("feed", False))
        if candidate:
            candidates.append(candidate)
    # Prefer actual boards/feeds over individual job pages. If a parent careers
    # page is itself present, its child URLs do not need separate source setups.
    parents = [item["url"] for item in candidates if item["kind"] == "html"]
    candidates = [item for item in candidates if item["kind"] != "html" or not any(
        item["url"] != parent and item["url"].startswith(parent.rstrip("/") + "/") for parent in parents)]
    candidates.sort(key=lambda item: 2 if item["kind"] == "html" else 1 if item["kind"] == "feed" else 0)
    return merge_candidates([], candidates, limit=20)
