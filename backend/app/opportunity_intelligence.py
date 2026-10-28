"""Evidence-backed relevance and next steps for internships and hackathons.

Listing text and optional AI interpretation never authorize an application. Hackathon
rules are assessed separately: an event has no unstated employment/degree condition.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone

from . import matching


def _strings(value) -> list[str]:
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _aware_date(value):
    """A date without a timezone is insufficient to assert an exact deadline."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _deadline_urgency(data: dict, now: datetime, *, hackathon: bool) -> str:
    deadline = _aware_date(data.get("deadline"))
    end = _aware_date(data.get("ends_at")) if hackathon else None
    if any(value and value <= now for value in (deadline, end)):
        return "expired"
    # starts_at deliberately does not participate in deadline calculation.
    target = deadline or (end if not data.get("deadline") else None)
    if not target:
        return "unknown"
    seconds = (target - now).total_seconds()
    for limit, label in [(86400, "within_24h"), (3 * 86400, "within_3d"), (7 * 86400, "within_7d")]:
        if seconds <= limit:
            return label
    return "later"


def _listed_skills(data: dict) -> list[str]:
    skills = _strings(data.get("skills"))
    text = matching.plain_text(str(data.get("description") or ""))
    skills.extend(skill for skill, pattern in matching.SKILLS.items() if re.search(pattern, text, re.I))
    return sorted({value.casefold(): value for value in skills}.values(), key=str.casefold)


def _skill_comparison(data: dict, profile: dict) -> tuple[list[str], list[str]]:
    candidates = {skill.casefold(): skill for skill in _strings(profile.get("skills"))} if "skills" in (profile.get("verified_fields") or []) else {}
    listed = _listed_skills(data)
    return sorted({candidates[skill.casefold()] for skill in listed if skill.casefold() in candidates}), [skill for skill in listed if skill.casefold() not in candidates]


def _sentences(text: str) -> list[str]:
    # Preserve U.S./U.K. and other dotted abbreviations in quoted evidence.
    boundaries = [0]
    for match in re.finditer(r"[\n;]+|(?<=[.!?])\s+", text):
        if not re.search(r"(?:\b[A-Za-z]\.){2,}$", text[:match.start()]):
            boundaries.extend([match.start(), match.end()])
    boundaries.append(len(text))
    return [text[boundaries[i]:boundaries[i + 1]].strip() for i in range(0, len(boundaries) - 1, 2) if text[boundaries[i]:boundaries[i + 1]].strip()]


def _countries(text: str) -> set[str]:
    aliases = {**matching.COUNTRIES, "us": "United States", "u.s": "United States", "u.k.": "United Kingdom"}
    return {country for token, country in aliases.items() if re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", text, re.I)}


def _numeric_bounds(text: str, *, age: bool) -> tuple[int | None, int | None]:
    minimum = maximum = None
    span = re.search(r"\b(?:between\s+)?(\d+)\s*(?:[-–—]|to|and)\s*(\d+)\b", text)
    if span:
        minimum, maximum = int(span[1]), int(span[2])
    for pattern in [r"(?:at least|minimum(?: of)?|min(?:imum)?(?: team)? size[: ]*)\s*(\d+)", r"\b(\d+)\s*(?:\+|or older|and older|or above|and above)"]:
        match = re.search(pattern, text)
        if match:
            minimum = max(minimum or 0, int(match[1]))
    for pattern in [r"(?:at most|maximum(?: of)?|up to|no more than)\s*(\d+)", r"\b(\d+)\s*(?:or younger|or below|and below)"]:
        match = re.search(pattern, text)
        if match:
            maximum = min(maximum if maximum is not None else int(match[1]), int(match[1]))
    if age:
        for pattern, adjustment, bound in [(r"\b(?:over|older than)\s*(\d+)", 1, "min"), (r"\b(?:under|younger than)\s*(\d+)", -1, "max")]:
            match = re.search(pattern, text)
            if match:
                value = int(match[1]) + adjustment
                if bound == "min": minimum = max(minimum or value, value)
                else: maximum = min(maximum if maximum is not None else value, value)
    if minimum is None and maximum is None:
        exact = re.search(r"(?:teams? of|team size(?: (?:must be|is))?[: ]*|exactly)\s*(\d+)\b", text)
        if exact:
            minimum = maximum = int(exact[1])
    return minimum, maximum


def _positive_prize(text: str) -> bool:
    currency = r"(?:[₹$€£]|\b(?:inr|usd|eur|gbp|cad|aud|sgd)\b)"
    amount = r"\d[\d,]*(?:\.\d+)?"
    for sentence in _sentences(text):
        if not re.search(r"\b(?:prizes?|rewards?|bount(?:y|ies))\b", sentence, re.I) or re.search(r"\b(?:may|might|potential|conditional|tbd|undisclosed|not guaranteed|no (?:cash )?prizes?)\b", sentence, re.I):
            continue
        values = re.findall(rf"{currency}\s*({amount})(?:\s*[-–—]\s*({amount}))?|({amount})\s*{currency}", sentence, re.I)
        if any(math.isfinite(float(value.replace(",", ""))) and float(value.replace(",", "")) > 0 for group in values for value in group if value):
            return True
    return False


def _interest_matches(data: dict, profile: dict) -> list[str]:
    text = " ".join([str(data.get("title") or ""), matching.plain_text(str(data.get("description") or "")), *_strings(data.get("tags")), *_listed_skills(data)]).casefold()
    aliases = {
        "ai ml": r"\bai\b|\bml\b|artificial intelligence|machine learning|deep learning",
        "cloud": r"\bcloud\b|\baws\b|\bazure\b|\bgcp\b",
        "cloud computing": r"\bcloud\b|\baws\b|\bazure\b|\bgcp\b",
        "web development": r"\bweb\b|front.?end|back.?end|full.?stack",
    }
    matches = []
    for interest in _strings(profile.get("hackathon_interests")):
        normalized = " ".join(re.findall(r"[a-z0-9]+", interest.casefold()))
        if normalized and re.search(aliases.get(normalized, r"\b" + r"\W+".join(map(re.escape, normalized.split())) + r"\b"), text):
            matches.append(interest)
    return sorted(set(matches))


def _evaluate_hackathon(data: dict, profile: dict, now: datetime) -> dict:
    text = matching.plain_text(str(data.get("description") or ""))
    fields = set(_strings(profile.get("verified_fields")))
    reasons, verified, inferred = [], [], []
    uncertain = rejected = False
    open_quotes = []

    def review(message: str, quote: str):
        nonlocal uncertain, rejected
        answer = (profile.get("verified_answers") or {}).get(quote)
        if isinstance(answer, dict) and answer.get("verified") is True and answer.get("eligible") is True:
            verified.append("Verified answer for the exact rule: " + quote)
        elif isinstance(answer, dict) and answer.get("verified") is True and answer.get("eligible") is False:
            rejected = True; reasons.append("Your verified answer does not meet the rule: " + quote)
        else:
            uncertain = True; reasons.append(message + ': "' + quote + '"')

    def reject(message: str, quote: str):
        nonlocal rejected
        rejected = True; reasons.append(message + ': "' + quote + '"')

    for sentence in _sentences(text):
        lower = sentence.casefold()
        preferred = bool(re.search(r"\bprefer(?:red|ably|ence)|nice to have|bonus|desirable\b", lower))
        negated = bool(re.search(r"\b(?:not|except|excluding|excluded|ineligible|cannot|can't|without)\b", lower))
        open_rule = bool(re.search(r"\bopen to (?:all|everyone|anyone)\b|\b(?:anyone|everyone) (?:can|may) (?:participate|register|join)\b|\b(?:participants?|participation|applicants?|eligibility|registration|open)\b.{0,60}\b(?:worldwide|globally|anywhere in the world|all countries)\b", lower))
        if open_rule and not negated and not preferred:
            open_quotes.append(sentence)
        # Split newly introduced mandatory predicates without splitting skill lists
        # or numeric ranges ("between 2 and 4", "Python and Rust").
        clauses = re.split(r",\s*(?=(?:must|requires?|only)\b)|\band\s+(?=(?:must|provide|submit|hold|possess|pay|attend|be available)\b)", sentence, flags=re.I)
        for clause in clauses:
            low = clause.casefold()
            hard = bool(re.search(r"\bmust\b|\brequir\w*\b|\bonly\b|\bat least\b|\bat most\b|\bminimum\b|\bmaximum\b|\brestricted\b|\blimited to\b", low)) or len(clauses) > 1
            # Clearly stated restrictions can omit the word "must".
            hard = hard or bool(re.search(r"\b(?:teams? of|team size|aged?\s+\d|residents? of|students? only)\b", low))
            if preferred:
                continue
            handled = False
            if negated and (open_rule or hard):
                review("A negative or exception clause needs interpretation", clause)
            geo = bool(re.search(r"\b(?:must|need to|required to)\b.{0,40}\b(?:based|resident|reside|located|live)\b|\b(?:only|restricted|limited)\b.{0,45}\b(?:residents?|citizens?|participants?|students?|teams?|people|developers?)\b|\b(?:residents?|citizens?)\b.{0,45}\b(?:only|eligible)\b|\bopen to (?:residents?|participants? from|students? in)\b", low))
            if geo:
                handled = True
                countries = _countries(clause)
                country = profile.get("country")
                if not countries or "country" not in fields or not isinstance(country, str) or not country:
                    review("Verify the geographic participation requirement", clause)
                elif negated:
                    if country.casefold() in {item.casefold() for item in countries}:
                        reject("Your verified country is explicitly excluded", clause)
                elif country.casefold() not in {item.casefold() for item in countries}:
                    reject("Your verified country does not meet the participation restriction", clause)
                else:
                    verified.append("Verified country matches the rule: " + clause)
            age_rule = bool(re.search(r"\bage\b|\baged\b|\byears? old\b|\badults?\b|\bminors?\b", low))
            team_rule = bool(re.search(r"\bteam(?:s| size)?\b", low))
            for applies, field, label in [(age_rule, "age", "age"), (team_rule, "team_size", "team size")]:
                if not applies or not hard:
                    continue
                handled = True
                minimum, maximum = _numeric_bounds(low, age=field == "age")
                value = profile.get(field)
                if negated or minimum is None and maximum is None:
                    review("Verify the " + label + " rule", clause)
                elif field not in fields or not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    review("Confirm your " + label + " against the rule", clause)
                elif minimum is not None and value < minimum or maximum is not None and value > maximum:
                    reject("Your verified " + label + " does not meet the rule", clause)
                else:
                    verified.append("Your verified " + label + " meets the rule: " + clause)
            academic = bool(re.search(r"graduat|class of|bachelor|undergraduat|master|ph\.?d|doctor|\bstudents?\b|\bdegree\b|\benrolled\b", low))
            technical = [skill for skill, pattern in matching.SKILLS.items() if re.search(pattern, clause, re.I)]
            skill_rule = technical and bool(re.search(r"\bmust\b|\brequir|\bneed\b|\bessential\b|\bproficien|knowledge of|experience (?:with|in)", low))
            if (academic or skill_rule) and hard:
                req = matching.extract_requirements(clause)
                if academic:
                    handled = True
                    constraints = req.get("graduation_constraints") or []
                    if constraints:
                        year = profile.get("graduation_year")
                        if "graduation_year" not in fields or not isinstance(year, int) or isinstance(year, bool):
                            review("Verify your graduation year for this stated rule", clause)
                        elif any((item["years"] and year not in item["years"]) or item["min"] is not None and year < item["min"] or item["max"] is not None and year > item["max"] for item in constraints):
                            reject("Your verified graduation year does not meet the stated rule", clause)
                        else:
                            verified.append("Your verified graduation year meets the rule: " + clause)
                    levels = req.get("degree_groups") or []
                    if levels:
                        level = matching._degree_level(str(profile.get("degree") or ""))
                        if "degree" not in fields or level is None:
                            review("Verify your degree for this stated rule", clause)
                        elif any(level not in group for group in levels):
                            reject("Your verified degree does not meet the stated rule", clause)
                        else:
                            verified.append("Your verified degree meets the rule: " + clause)
                    if not constraints and not levels:
                        review("Verify the stated academic or enrollment condition", clause)
                if skill_rule:
                    handled = True
                    candidate = {value.casefold() for value in _strings(profile.get("skills"))} if "skills" in fields else set()
                    groups = req.get("required_skill_groups") or []
                    if not groups:
                        review("Interpret the mandatory technical condition", clause)
                    for group in groups:
                        if not candidate.intersection(value.casefold() for value in group):
                            review("Verify required proficiency in " + " or ".join(group), clause)
                # Retain actual uncertainty; discard internship-only missing-field defaults.
                for detail in req["uncertain"]:
                    if not detail.startswith(("Graduation-year eligibility is not", "Academic requirements require", "Geographic/work-authorization eligibility is not")):
                        review(detail.split(":", 1)[0], clause)
            attendance = bool(re.search(r"\bavailable\b|\bavailability\b|\battend\b|\battendance\b", low))
            if attendance and hard:
                handled = True
                start, end = _aware_date(data.get("starts_at")), _aware_date(data.get("ends_at"))
                try:
                    available_start = date.fromisoformat(str(profile.get("availability_start"))) if "availability_start" in fields else None
                    available_end = date.fromisoformat(str(profile.get("availability_end"))) if "availability_end" in fields else None
                except (ValueError, TypeError):
                    available_start = available_end = None
                if not all((start, end, available_start, available_end)):
                    review("Verify availability and the exact required attendance dates", clause)
                elif available_start > start.date() or available_end < end.date():
                    reject("Your verified availability does not cover required attendance", clause)
                else:
                    verified.append("Your verified availability covers the stated attendance dates: " + clause)
            sensitive = bool(re.search(r"\bcitizen|\bvisa\b|work authori|right to work|legally.{0,20}work|security clearance|\bgpa\b|\bcgpa\b|\bmarks\b|degree in|major(?:ing)? in|\bfees?\b|\bpay(?:ment)?\b|\bcertification\b|\bpassport\b|\bidentification\b", low))
            if hard and (sensitive or not handled):
                review("Verify this mandatory participation condition", clause)
    if not open_quotes:
        uncertain = True; inferred.append("The description does not explicitly confirm open participation; remote/location metadata is insufficient.")
    else:
        verified.extend('Explicit participation statement: "' + quote + '"' for quote in open_quotes)
    urgency = _deadline_urgency(data, now, hackathon=True)
    if urgency == "expired":
        rejected = True; reasons.append("The stated deadline has passed or the event has ended.")
    for field in ("deadline", "ends_at"):
        if data.get(field) and _aware_date(data[field]) is None:
            review("Verify the date and timezone for " + field, str(data[field]))
    overlap, missing = _skill_comparison(data, profile)
    score = 25
    signals = ["Base relevance (+25)."]
    if open_quotes:
        score += 15; signals.append("Explicit open-participation statement (+15).")
    listed = _listed_skills(data)
    if overlap and listed:
        points = round(30 * len(overlap) / len(listed)); score += points
        signals.append("Verified skill overlap: " + ", ".join(overlap) + f" (+{points}).")
        verified.append("Verified skill overlap: " + ", ".join(overlap))
    interests = _interest_matches(data, profile)
    if interests:
        points = min(15, 5 * len(interests)); score += points
        signals.append("Matches selected hackathon interests: " + ", ".join(interests) + f" (+{points}).")
    country = profile.get("country")
    from .geography import classify
    geography = classify(data, profile)
    if "country" in fields and isinstance(country, str) and country in geography["countries"]:
        score += 8; signals.append("Listed location matches your verified country (+8); location does not establish eligibility.")
    if geography["local_matches"]:
        score += 3; signals.append("Listed in a preferred local city or its nearby cluster: " + ", ".join(geography["local_matches"]) + " (+3); participation eligibility is assessed separately.")
    if profile.get("remote_preferred") is True and data.get("remote") is True:
        score += 3; signals.append("Matches remote-work preference (+3).")
    if urgency in {"within_24h", "within_3d", "within_7d"}:
        score += 8; signals.append("A stated deadline or event end is within seven days (+8).")
    if _positive_prize(text):
        score += 4; signals.append("A positive prize amount is disclosed in the description (+4); awards are conditional on event rules and results.")
    eligibility = "ineligible" if rejected else "review" if uncertain else "eligible"
    if not reasons:
        reasons.append("Explicit participation rules match the verified information available." if eligibility == "eligible" else "Review the official participation rules before registering.")
    return {"score": min(24, score) if rejected else min(100, score), "eligibility": eligibility,
            "reasons": list(dict.fromkeys(reasons)), "verified": list(dict.fromkeys(verified)),
            "inferred": list(dict.fromkeys(inferred)), "skill_overlap": overlap,
            "missing_skills": missing, "ranking_signals": signals, "deadline_urgency": urgency}


def evaluate_opportunity(data: dict, profile: dict) -> dict:
    """Preserve internship guardrails and enrich both kinds with actionable context."""
    now = datetime.now(timezone.utc)
    hackathon = str(data.get("opportunity_type") or "internship").casefold() == "hackathon"
    if hackathon:
        result = _evaluate_hackathon(data, profile, now)
    else:
        result = dict(matching.evaluate(data, profile))
        result["missing_skills"] = _skill_comparison(data, profile)[1]
        result["deadline_urgency"] = _deadline_urgency(data, now, hackathon=False)
        result.setdefault("ranking_signals", [])
        if result["eligibility"]!="ineligible":
            text = " ".join([str(data.get("title") or ""),matching.plain_text(str(data.get("description") or ""))]).casefold()
            aliases = {"software engineering":r"software engineer|software develop|\bswe\b", "ai/ml":r"machine learning|artificial intelligence|\bml\b|\bai\b", "data science":r"data scien", "cloud engineering":r"\bcloud\b|\baws\b|\bazure\b", "cybersecurity":r"cyber.?security|security engineer", "web development":r"web develop|front.?end|full.?stack|back.?end", "research":r"\bresearch\b"}
            roles = [role for role in _strings(profile.get("preferred_roles")) if re.search(aliases.get(role.casefold(),re.escape(role.casefold())),text)]
            if roles:
                points = min(6,3*len(roles))
                result["score"] = min(100,result["score"]+points)
                result["ranking_signals"].append("Matches selected roles: "+", ".join(roles)+f" (+{points}).")
    if result["eligibility"] == "ineligible":
        action = "Keep for reference; this opportunity is closed or a stated requirement does not match your verified profile."
    elif result["eligibility"] == "review":
        action = "Review the quoted rules and verify the missing eligibility information on the official opportunity page."
    elif result["deadline_urgency"] == "unknown":
        action = "Check the official deadline and event details, then register." if hackathon else "Check the official deadline, then prepare your application."
    else:
        action = "Review the official rules and register before the stated deadline." if hackathon else "Prepare and review your application before the stated deadline."
    result["recommended_action"] = action
    return result
