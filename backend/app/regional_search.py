"""Bounded, user-enabled discovery lanes; search references are never eligibility.

Employer discovery deliberately searches beyond known ATS boards. Those results
are source proposals for review, not permission to crawl a new organization's
website. API keys stay server-side.
"""
from __future__ import annotations

import os
import re
from .geography import local_cities

MAX_SEARCH_SOURCES = 64
MAX_QUERY_LENGTH = 200


def _place(value: str) -> str:
    # City names are quoted data, never user-supplied search operators.
    return " ".join(re.findall(r"[\w'-]+", value))[:100].strip()


def search_freshness(source: dict) -> str | None:
    """Directory/program discovery needs more coverage than weekly job alerts."""
    label = source.get("company", "").casefold()
    # Durable directories often have no recent publication date. A freshness
    # filter here would systematically hide lesser-known, established teams.
    if "employer discovery" in label:
        return None
    return "pm" if "research programs" in label else "pw"


def search_sources(profile: dict | None = None) -> list[dict]:
    profile = profile or {}
    result: list[dict] = []
    seen: set[str] = set()

    def add(region: str, lane: str, terms: str, location: str, interval: int = 21600):
        query = f"{terms} ({location})"
        if len(query) > MAX_QUERY_LENGTH or query in seen:
            return
        seen.add(query)
        result.append({"kind": "search", "slug": query, "company": f"{region} {lane}"[:200],
                       "permitted": True, "enabled": True, "interval_seconds": interval})

    # Independent lanes avoid requiring software AND AI AND research in every
    # result. Broader titles find small firms that do not use standard ATS names.
    global_lanes = (
        ("India", "internship search", '(internship OR "project intern") (software OR research)', "India"),
        ("India", "hackathon search", '(hackathon OR "innovation competition") registration', "India"),
        ("India", "research programs", '("summer student" OR "research assistant" OR internship) (university OR institute)', "India"),
        ("India", "employer discovery", '(startup OR incubator OR "technology park") (careers OR portfolio OR companies)', "India"),
        ("Remote", "internship search", '(internship OR "student developer") (remote OR "work from home")', "India"),
        ("Remote", "hackathon search", '(hackathon OR "coding challenge") (online OR virtual) registration', "India OR worldwide"),
        ("International", "internship search", 'internship ("Indian students" OR "open worldwide" OR "all nationalities")', "international OR abroad OR remote"),
        ("International", "hackathon search", 'hackathon ("open worldwide" OR "Indian students" OR "all countries")', "international OR online"),
    )
    local_lanes = (
        ("internship search", '(internship OR "project intern" OR "student developer") (software OR research)'),
        ("hackathon search", '(hackathon OR "coding challenge" OR "innovation competition") registration'),
        ("student roles search", '("graduate trainee" OR "research assistant" OR "summer student")'),
        ("startup internships search", '(startup OR "small company") (internship OR trainee) careers'),
        ("employer discovery", '(incubator OR "entrepreneurship cell" OR "technology park") (portfolio OR companies)'),
        ("research programs", '(internship OR "student program") (university OR college OR laboratory)'),
    )
    nearby = {"nagpur": 'Nagpur OR MIHAN OR Butibori', "pune": 'Pune OR Hinjawadi OR "Pimpri Chinchwad"'}
    targets = []
    names = set()
    for raw in local_cities(profile)[:20]:
        city = _place(raw)
        if not city or city.casefold() in names:
            continue
        names.add(city.casefold())
        location = nearby.get(city.casefold(), f'"{city}"') if profile.get("include_nearby_locations", True) else f'"{city}"'
        targets.append((city, location))
    # Round robin gives every selected city its basic internship/hackathon lanes
    # before allocating exploratory queries. Always reserve national/remote lanes.
    for lane, terms in local_lanes:
        for region, location in targets:
            if len(result) >= MAX_SEARCH_SOURCES - len(global_lanes):
                break
            add(region, lane, terms, location)
    for region, lane, terms, location in global_lanes:
        add(region, lane, terms, location)
    return result


def configured() -> bool:
    return bool(os.environ.get("BRAVE_SEARCH_API_KEY"))
