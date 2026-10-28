"""Location browsing, separate from residence, visa and participation eligibility.

Only listing location/venue metadata is used. Company names, query text and a
mention of India in the description never establish the opportunity's location.
Nearby places are named clusters, not a claimed distance or commute estimate.
"""
from __future__ import annotations

import re
import unicodedata

LOCAL_CITIES = ("Nagpur", "Pune")
NEARBY = {
    "nagpur": ("Nagpur", "MIHAN", "Butibori", "Hingna", "Kamptee"),
    "pune": ("Pune", "Poona", "Pimpri", "Chinchwad", "PCMC", "Hinjawadi", "Hinjewadi", "Wakad", "Chakan", "Talegaon"),
}
COUNTRY_PLACES = {
    "India": ("India", "Bharat", "Maharashtra", "Nagpur", "Pune", "Poona", "Mumbai", "Bombay", "Bengaluru", "Bangalore", "Hyderabad", "Chennai", "Delhi", "Noida", "Gurugram", "Gurgaon", "Kolkata", "Ahmedabad", "Jaipur", "Indore", "Kochi", "Coimbatore", "Chandigarh", "Bhubaneswar", "Nashik", "Aurangabad", *NEARBY["nagpur"], *NEARBY["pune"]),
    "United States": ("United States", "USA", "U.S.A.", "U.S.", "New York", "San Francisco", "Seattle", "Boston", "California", "Austin", "Chicago"),
    "United Kingdom": ("United Kingdom", "UK", "U.K.", "London, UK", "London, England", "England", "Scotland"),
    "Canada": ("Canada", "Toronto", "Vancouver", "Montreal"),
    "Germany": ("Germany", "Berlin", "Munich"),
    "Singapore": ("Singapore",), "Australia": ("Australia", "Sydney", "Melbourne"),
    "Netherlands": ("Netherlands", "Amsterdam"), "Ireland": ("Ireland", "Dublin"),
    "France": ("France", "Paris"), "Japan": ("Japan", "Tokyo"),
    "United Arab Emirates": ("United Arab Emirates", "UAE", "Dubai", "Abu Dhabi"),
    "Switzerland": ("Switzerland", "Zurich", "Zürich"), "South Korea": ("South Korea", "Seoul"),
}
COUNTRY_CODES = {"IN": "India", "US": "United States", "GB": "United Kingdom", "CA": "Canada", "DE": "Germany", "SG": "Singapore", "AU": "Australia", "NL": "Netherlands", "IE": "Ireland", "FR": "France", "JP": "Japan", "AE": "United Arab Emirates", "CH": "Switzerland", "KR": "South Korea"}


def normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", str(value)).casefold()))


def mentions(text: str, place: str) -> bool:
    place = normalized(place)
    return bool(place and re.search(r"(?<!\w)" + re.escape(place) + r"(?!\w)", normalized(text)))


def local_cities(profile: dict) -> list[str]:
    return [s.strip() for s in profile.get("preferred_local_cities", LOCAL_CITIES) if isinstance(s, str) and s.strip()]


def city_matches(location: str, city: str, nearby: bool = True) -> bool:
    aliases = NEARBY.get(normalized(city), (city,)) if nearby else (("Pune", "Poona") if normalized(city) == "pune" else (city,))
    return any(mentions(location, alias) for alias in aliases)


def location_matches(job: dict, query: str, nearby: bool = True) -> bool:
    if normalized(query) == "india":
        return "india" in classify(job, {})["regions"]
    return city_matches(str(job.get("location") or ""), query, nearby)


def classify(job: dict, profile: dict) -> dict:
    location = str(job.get("location") or "")
    venue_country = str(job.get("venue_country") or "").strip()
    countries = {country for country, places in COUNTRY_PLACES.items() if any(mentions(location, place) for place in places)}
    # Unstructured short codes can also be US states (CA, IN, DE). Accept a
    # whole-location code, or unambiguous US/UK markers; venue_country is typed
    # publisher metadata and can use the full code table.
    if location.strip() in COUNTRY_CODES:
        countries.add(COUNTRY_CODES[location.strip()])
    for component in re.split(r"[,;/|]|\s+-\s+", location):
        if component.strip() in {"US", "GB", "UK"}:
            countries.add("United States" if component.strip()=="US" else "United Kingdom")
    if venue_country in COUNTRY_CODES:
        countries.add(COUNTRY_CODES[venue_country])
    for country, places in COUNTRY_PLACES.items():
        if any(normalized(venue_country) == normalized(place) for place in (country, *places)):
            countries.add(country)
    matches = [city for city in local_cities(profile) if city_matches(location, city, profile.get("include_nearby_locations", True))]
    regions = []
    if matches:
        regions.append("local")
    if "India" in countries:
        regions.append("india")
    if countries - {"India"}:
        regions.append("international")
    worldwide = bool(re.search(r"\b(?:worldwide|world wide|anywhere in the world|global(?:ly)? remote|remote globally|all countries)\b", location, re.I))
    if worldwide:
        regions.append("worldwide")
    if not regions:
        regions.append("unknown")
    return {"regions": regions, "countries": sorted(countries), "local_matches": matches,
            "basis": "listing_location_metadata", "eligibility_note": "Location does not confirm visa, work authorization, worldwide participation, or acceptance of Indian applicants."}


def preferred_location(job: dict, profile: dict) -> bool:
    return any((normalized(value) == "remote" and job.get("remote") is True) or location_matches(job, value, profile.get("include_nearby_locations", True)) for value in profile.get("preferred_locations", []) if isinstance(value, str) and value.strip())
