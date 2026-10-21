"""Conservative, evidence-backed extraction and deterministic candidate matching.

Job descriptions and LLM suggestions are untrusted. Only requirements extracted with
an evidence quote can establish eligibility. Unknown critical requirements stay review.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}: self.skip += 1
        if tag in {"p", "br", "li", "div", "h1", "h2", "h3"}: self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip: self.skip -= 1
        if tag in {"p", "li", "div"}: self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _TextParser(); parser.feed(unescape(value or ""))
    return re.sub(r"[ \t]+", " ", "".join(parser.parts)).strip()


SKILLS = {
    "Python": r"\bpython\b", "JavaScript": r"\bjavascript\b", "TypeScript": r"\btypescript\b",
    "Java": r"\bjava\b", "C++": r"(?<!\w)c\+\+(?!\w)", "C": r"\bC programming\b",
    "C#": r"(?<!\w)c#(?!\w)", "Go": r"\bgolang\b|\bGo programming\b",
    "Rust": r"\brust\b", "SQL": r"\bsql\b", "React": r"\breact(?:\.js)?\b",
    "Next.js": r"\bnext\.?js\b", "Node.js": r"\bnode\.?js\b", "HTML": r"\bhtml\b",
    "CSS": r"\bcss\b", "Git": r"\bgit\b", "Linux": r"\blinux\b", "Docker": r"\bdocker\b",
    "Kubernetes": r"\bkubernetes\b", "AWS": r"\baws\b|amazon web services",
    "Azure": r"\bazure\b", "GCP": r"\bgcp\b|google cloud", "PyTorch": r"\bpytorch\b",
    "TensorFlow": r"\btensorflow\b", "Machine Learning": r"\bmachine learning\b",
    "AI": r"\bartificial intelligence\b|\bAI\b", "Cloud": r"\bcloud computing\b",
    "Data Structures": r"\bdata structures\b", "Algorithms": r"\balgorithms\b",
}

COUNTRIES = {"india": "India", "united states": "United States", "usa": "United States",
             "u.s.": "United States", "united kingdom": "United Kingdom", "uk": "United Kingdom",
             "canada": "Canada", "germany": "Germany", "australia": "Australia",
             "singapore": "Singapore", "netherlands": "Netherlands", "ireland": "Ireland"}


_GRADUATION_PERIOD = r"(?:january|february|march|april|may|june|july|august|september|october|november|december|spring|summer|fall|autumn|winter)"


def _graduation_constraint(context: str, years: list[int]) -> dict | None:
    """Keep both bounds and distinguish strict year bounds from partial dates."""
    constraint = {"years": [], "min": None, "max": None}
    year = r"20[2-4]\d"
    dated_year = rf"(?:{_GRADUATION_PERIOD}\s+)?{year}"
    # "Before 2028 or after 2030" describes separate windows, not two AND bounds.
    if re.search(rf"{year}\s*,?\s*or\s+(?:graduat\w*\s+)?(?:after|before|later than|prior to|no earlier than|no later than|on or after|on or before)\s+{dated_year}", context, re.I):
        return None
    inclusive = [
        ("min", rf"(?:no earlier than|not before|on or after|at least)\s+{dated_year}|{year}\s*(?:or later|onwards?|and beyond|or after|or beyond)"),
        ("max", rf"(?:no later than|not after|on or before|by)\s+{dated_year}|{year}\s*(?:or earlier|or before|and prior)"),
    ]
    occupied = []
    for bound, pattern in inclusive:
        for match in re.finditer(pattern, context, re.I):
            value = int(re.search(year, match.group()).group())
            previous = constraint[bound]
            constraint[bound] = value if previous is None else (max(previous, value) if bound == "min" else min(previous, value))
            occupied.append(match.span())
    for bound, pattern, adjustment in [
        ("min", rf"(?:after|later than)\s+{dated_year}", 1),
        ("max", rf"(?:before|prior to)\s+{dated_year}", -1),
    ]:
        for match in re.finditer(pattern, context, re.I):
            if any(start <= match.start() and match.end() <= end for start, end in occupied):
                continue
            value = int(re.search(year, match.group()).group())
            # A year-only profile cannot resolve "after May 2029" within 2029.
            if not re.search(_GRADUATION_PERIOD, match.group(), re.I):
                value += adjustment
            previous = constraint[bound]
            constraint[bound] = value if previous is None else (max(previous, value) if bound == "min" else min(previous, value))
    if constraint["min"] is not None and constraint["max"] is not None and constraint["min"] > constraint["max"] and re.search(r"\bor\b", context):
        return None
    if constraint["min"] is None and constraint["max"] is None:
        if len(years) == 2 and re.search(r"between|20\d{2}\s*[-–—]\s*20\d{2}|20\d{2}\s+to\s+20\d{2}", context, re.I):
            constraint["years"] = list(range(min(years), max(years) + 1))
        else:
            constraint["years"] = years
    return constraint


def extract_requirements(description: str, *, location: str = "", title: str = "") -> dict:
    """Extract explicit statements, preserving quotes. A posting's summer year is not graduation."""
    text = plain_text(description)
    result: dict = {"graduation_years": [], "graduation_constraints": [], "excluded_graduation_years": [], "graduation_min": None, "graduation_max": None,
                    "degree_levels": [], "degree_groups": [], "countries": [], "country_groups": [], "excluded_countries": [], "work_authorization": None,
                    "min_experience_years": None, "skills": [], "required_skill_groups": [], "evidence": [], "uncertain": [], "preferences": []}
    sentences = [s.strip() for s in re.split(r"[\n;]|(?<=[.!?])\s+", text) if s.strip()]
    for sentence in sentences:
        lower = sentence.lower()
        # Exclude salary, start dates, company history, and internship dates.
        preferred = bool(re.search(r"prefer(?:red|ably|ence)|nice to have|bonus|desirable", lower))
        grad = re.search(r"graduat(?:e|es|ing|ion)|class of|complet(?:e|ing|ion).{0,35}(?:degree|studies)", lower)
        years = [int(y) for y in re.findall(r"\b20[2-4]\d\b", sentence)]
        negated = bool(re.search(r"\b(?:not eligible|ineligible|must not|cannot|can not|may not|not permitted|not accepted|excluding|excluded|except)\b", lower))
        if negated:
            result["uncertain"].append("A negative eligibility statement requires review: " + sentence[:1000])
            result["evidence"].append({"field": "negative_eligibility", "quote": sentence[:1000]})
        if grad and years and negated:
            result["excluded_graduation_years"].extend(years)
            result["evidence"].append({"field": "excluded_graduation_years", "quote": sentence[:1000]})
        if grad and years and preferred and not negated:
            result["preferences"].append({"field": "graduation_years", "quote": sentence[:1000]})
        if grad and years and not preferred and not negated:
            # Link a year closely to graduation text. Very long paragraphs are ambiguous.
            raw_fragments = re.findall(r"(?:graduat\w*|class of|complet\w*).{0,140}", sentence, re.I)
            fragments, relevant = [], []
            months = _GRADUATION_PERIOD
            for fragment in raw_fragments:
                fragment = re.split(r"\b(?:internship|employment|role|position|starts?|starting|begins?|beginning|available|availability|join|application|deadline)\b", fragment, maxsplit=1, flags=re.I)[0]
                fragments.append(fragment)
                matches = list(re.finditer(r"\b20[2-4]\d\b", fragment))
                if not matches:
                    continue
                relevant.append(int(matches[0].group()))
                for previous, current in zip(matches, matches[1:]):
                    connector = fragment[previous.end():current.start()].lower()
                    if not re.fullmatch(r"\s*(?:(?:[,()/]|or|and|to|[-–—])\s*)+(?:" + months + r"\s+)?", connector):
                        break
                    relevant.append(int(current.group()))
            # Leading years must directly modify graduates; unrelated summer dates do not.
            leading = re.finditer(r"((?:20[2-4]\d)(?:\s*(?:or|and|to|[-–—/])\s*20[2-4]\d)*)(?:\s+(?:college|university))?\s+graduat(?:es|ing|e)\b", sentence, re.I)
            for match in leading:
                phrase = match.group(1)
                relevant.extend(int(y) for y in re.findall(r"20[2-4]\d", phrase))
                fragments.append(match.group())
            relevant = sorted(set(relevant))
            graduation_context = " ".join(fragments).lower()
            if relevant:
                constraint = _graduation_constraint(graduation_context, relevant)
                if constraint is None:
                    result["uncertain"].append("Alternative graduation windows require manual interpretation: " + sentence[:1000])
                    result["evidence"].append({"field": "unsupported_requirement", "quote": sentence[:1000]})
                else:
                    if constraint["min"] is not None:
                        result["graduation_min"] = max(result["graduation_min"] or constraint["min"], constraint["min"])
                    if constraint["max"] is not None:
                        result["graduation_max"] = min(result["graduation_max"] or constraint["max"], constraint["max"])
                    result["graduation_years"].extend(constraint["years"])
                    result["graduation_constraints"].append(constraint)
                    result["evidence"].append({"field": "graduation_years", "quote": sentence[:1000]})
        # Do not promote preferred qualifications into hard requirements.
        hard = bool(re.search(r"\bmust\b|\brequir|\benrolled\b|\bpursuing\b|\bcurrently\b|\bstudent\b|\bcandidate\b", lower))
        degrees = []
        if re.search(r"bachelor|undergraduat|\bb\.?tech\b|\bb\.?sc\b|\bbs\b|\bba\b", lower): degrees.append("undergraduate")
        if re.search(r"master|\bm\.?tech\b|\bmsc\b|\bms\b", lower): degrees.append("masters")
        if re.search(r"ph\.?d|doctor(?:al|ate)", lower): degrees.append("phd")
        if degrees and hard and not preferred and not negated and not re.search(r"\b(?:no|not|without)\b", lower):
            result["degree_groups"].append(degrees)
            result["degree_levels"].extend(degrees)
            result["evidence"].append({"field": "degree_levels", "quote": sentence[:1000]})
        if degrees and re.search(r"\b(?:no|not|without)\b", lower) and hard:
            result["uncertain"].append("Negated academic requirements need manual interpretation: " + sentence[:1000])
        mandatory = hard or bool(re.search(r"\bat least\b|\bminimum\b|\bonly\b", lower))
        unsupported_academic = re.search(r"\bgpa\b|\bcgpa\b|grade.point|\bmarks\b|\bpercentage\b|\d+(?:\.\d+)?\s*%|(?:first|second|third|fourth|final|[1-4](?:st|nd|rd|th))[- ]year|degree in|major(?:ing)? in", lower)
        unsupported_personal = re.search(r"(?:minimum|at least|maximum).{0,20}\bage\b|\bage.{0,20}\d+|\bavailable\b|\bavailability\b|\bfull[- ]time\b|\bon[- ]site\b|\bonsite\b|\brelocat", lower)
        date_specific = grad and re.search(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december|spring|summer|fall|autumn|winter)\b", lower)
        if not preferred and (mandatory and (unsupported_academic or unsupported_personal) or date_specific):
            result["uncertain"].append("Unsupported mandatory eligibility detail requires review: " + sentence[:1000])
            result["evidence"].append({"field": "unsupported_requirement", "quote": sentence[:1000]})
        if re.search(r"citizen|work authori[sz]|authori[sz](?:ed|ation) (?:to )?work|right to work|legally.*work|sponsor|visa|security clearance", lower):
            existing = result["work_authorization"]
            result["work_authorization"] = ((existing + "\n") if existing else "") + sentence[:1000]
            result["evidence"].append({"field": "work_authorization", "quote": sentence[:1000]})
        if not preferred and re.search(r"(?:must|require|only|eligible|authori[sz]ed|based|resident|reside|located)", lower):
            if re.search(r"(?:must|only|require).{0,60}(?:based|resident|reside|located)|(?:based|resident|reside|located).{0,30}(?:only|required)", lower):
                found = [canonical for pattern, canonical in COUNTRIES.items() if re.search(r"(?<!\w)"+re.escape(pattern)+r"(?!\w)", lower)]
                if found:
                    target = "excluded_countries" if negated else "countries"
                    result[target].extend(found)
                    if target == "countries": result["country_groups"].append(found)
                    result["evidence"].append({"field": target, "quote": sentence[:1000]})
        experience = re.search(r"(?:at least|minimum(?: of)?|requires?|must have)?\s*(\d+)(?:\s*[-–—]\s*\d+)?\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:professional |relevant |industry |work )?experience", lower)
        if experience and not preferred:
            result["min_experience_years"] = max(result["min_experience_years"] or 0, int(experience.group(1)))
            result["evidence"].append({"field": "min_experience_years", "quote": sentence[:1000]})
        sentence_skills = []
        for skill, pattern in SKILLS.items():
            if re.search(pattern, sentence, re.I):
                result["skills"].append(skill)
                sentence_skills.append(skill)
        skill_mandate = bool(re.search(r"\bmust\b|\brequir|\bneed\b|\bessential\b|\bproficien|\bknowledge of\b|\bexperience (?:with|in)\b", lower))
        if sentence_skills and skill_mandate and not preferred:
            if negated or re.search(r"\b(?:no|not|without)\b", lower):
                result["uncertain"].append("Negated technical requirements need manual interpretation: " + sentence[:1000])
            elif re.search(r"\bor\b", lower) and re.search(r"\band\b", lower):
                result["uncertain"].append("Mixed alternative/mandatory technical requirements need manual interpretation: " + sentence[:1000])
            elif re.search(r"\bor\b|/", lower):
                result["required_skill_groups"].append(sentence_skills)
            else:
                result["required_skill_groups"].extend([[skill] for skill in sentence_skills])
            result["evidence"].append({"field": "required_skills", "quote": sentence[:1000]})
        explicit_mandate = bool(re.search(r"\bmust\b|\brequir|\bminimum\b|\bat least\b", lower))
        recognized = bool(degrees or grad and years or experience or sentence_skills and skill_mandate or any(item["quote"] == sentence[:1000] and item["field"] in {"countries", "excluded_countries", "work_authorization", "unsupported_requirement"} for item in result["evidence"]))
        no_experience_needed = bool(re.search(r"no (?:prior |previous |professional |work )?experience (?:is )?required|experience (?:is )?not required", lower))
        if explicit_mandate and not preferred and not recognized and not no_experience_needed:
            result["uncertain"].append("Unparsed mandatory condition requires human verification: " + sentence[:1000])
            result["evidence"].append({"field": "unsupported_requirement", "quote": sentence[:1000]})
    for key in ("graduation_years", "excluded_graduation_years", "degree_levels", "countries", "excluded_countries", "skills"):
        result[key] = sorted(set(result[key]))
    if not result["graduation_years"] and result["graduation_min"] is None and result["graduation_max"] is None:
        result["uncertain"].append("Graduation-year eligibility is not explicitly stated.")
    if not result["degree_levels"]:
        result["uncertain"].append("Academic requirements require review.")
    if not result["countries"]:
        result["uncertain"].append("Geographic/work-authorization eligibility is not explicitly confirmed.")
    return result


def _parse_date(value):
    if not value: return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (TypeError, ValueError): return None


def _degree_level(value: str):
    value = (value or "").lower()
    if re.search(r"ph\.?d|doctor", value): return "phd"
    if re.search(r"master|m\.?tech|m\.?sc|\bms\b", value): return "masters"
    if re.search(r"bachelor|undergrad|b\.?tech|b\.?sc|\bbs\b|\bba\b|b\.e\.", value): return "undergraduate"
    return None



def _normalized_topic(value: str) -> str:
    value = re.sub(r"\bengineer(?:ing|s)?\b", "engineer", value.casefold())
    value = re.sub(r"\bdevelop(?:ment|ers?|ing)\b", "develop", value)
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _interest_match(interest: str, job: dict) -> bool:
    title = _normalized_topic(job.get("title", ""))
    normalized = _normalized_topic(interest)
    if normalized and normalized in title:
        return True
    patterns = {
        "ai ml": r"\bai\b|\bml\b|artificial intelligence|machine learning|deep learning|applied scientist",
        "cloud computing": r"\bcloud\b|\baws\b|\bazure\b|\bgcp\b",
        "web develop": r"\bweb\b|front.?end|back.?end|full.?stack",
    }
    pattern = patterns.get(normalized)
    # Extracted job skills supplement abbreviated technical role titles.
    topics = title + " " + " ".join(str(skill).casefold() for skill in job.get("skills", []))
    return bool(pattern and re.search(pattern, topics))


def _disclosed_paid(compensation) -> bool:
    """A ranking bonus requires disclosed positive pay, never an invented stipend."""
    if not compensation:
        return False
    text = str(compensation).casefold()
    if re.search(r"\bunpaid\b|\bno (?:pay|compensation|stipend)\b|\bwithout (?:pay|compensation|stipend)\b|\bfor credit only\b", text):
        return False
    import json
    data = compensation
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            pass
    if isinstance(data, str) and re.search(r"\bpaid\b", text) and not re.search(r"\b(?:may|might|possibly|potentially|not guaranteed|depending on|subject to funding)\b", text):
        return True
    def positive_amount(value):
        if isinstance(value, dict):
            return any((str(key).casefold() in {"min", "max", "amount", "value", "salary", "minvalue", "maxvalue"} and isinstance(item, (int, float)) and not isinstance(item, bool) and item > 0) or positive_amount(item) for key, item in value.items())
        if isinstance(value, list):
            return any(positive_amount(item) for item in value)
        return False
    if positive_amount(data):
        return True
    if not isinstance(data, str):
        return False
    # Literal currency-bearing ranges, including a zero lower bound with paid upper bound.
    currency = r"(?:[₹$€£]|\b(?:inr|usd|eur|gbp|cad|aud|sgd)\b)"
    amount = r"\d[\d,]*(?:\.\d+)?"
    disclosed = re.findall(rf"{currency}\s*({amount})(?:\s*(?:[-–—]|to)\s*({amount}))?|({amount})\s*{currency}", text)
    if disclosed:
        return any(float(value.replace(",", "")) > 0 for values in disclosed for value in values if value)
    return False


def evaluate(job: dict, profile: dict) -> dict:
    """Deterministic guardrail. A numeric match score never grants eligibility."""
    req = job.get("requirements") or extract_requirements(job.get("description", ""), location=job.get("location", ""), title=job.get("title", ""))
    fields = set(profile.get("verified_fields") or [])
    reasons, verified, inferred = [], [], []
    rejection, uncertain = False, False
    score = 35
    now = datetime.now(timezone.utc)
    deadline = _parse_date(job.get("deadline"))
    if deadline and deadline <= now:
        rejection = True; reasons.append("The application deadline has passed.")
    elif deadline:
        verified.append(f"Application deadline: {deadline.date().isoformat()}")
        if (deadline - now).days <= 7: score += 8
    excluded_years = req.get("excluded_graduation_years") or []
    if "graduation_year" in fields and profile.get("graduation_year") in excluded_years:
        rejection = True; reasons.append("Your graduation year is explicitly excluded by the posting.")
    excluded_countries = req.get("excluded_countries") or []
    if "country" in fields and profile.get("country", "").casefold() in {c.casefold() for c in excluded_countries}:
        rejection = True; reasons.append("Your country is explicitly excluded by the posting.")
    if req.get("uncertain"):
        uncertain = True
        inferred.extend(str(value) for value in req["uncertain"])
    years = req.get("graduation_years") or []
    year_min, year_max = req.get("graduation_min"), req.get("graduation_max")
    if years or year_min is not None or year_max is not None:
        year = profile.get("graduation_year")
        if "graduation_year" not in fields or not isinstance(year, int) or isinstance(year, bool):
            uncertain = True; reasons.append("Confirm your expected graduation year.")
        elif (years and year not in years) or (year_min is not None and year < year_min) or (year_max is not None and year > year_max) or any((constraint.get("years") and year not in constraint["years"]) or (constraint.get("min") is not None and year < constraint["min"]) or (constraint.get("max") is not None and year > constraint["max"]) for constraint in req.get("graduation_constraints", [])):
            rejection = True; reasons.append(f"Graduation year {year} is outside the explicitly stated graduation requirement.")
        else:
            verified.append(f"Graduation year {year} meets the stated requirement."); score += 15
    else:
        uncertain = True; inferred.append("The posting does not explicitly confirm graduation-year eligibility.")
    levels = req.get("degree_levels") or []
    if levels:
        level = _degree_level(profile.get("degree", ""))
        if "degree" not in fields or not level:
            uncertain = True; reasons.append("Confirm your degree against the academic requirement.")
        elif level not in levels or any(level not in group for group in req.get("degree_groups", [])):
            rejection = True; reasons.append(f"Your verified {level} degree does not satisfy every mandatory academic clause in the posting.")
        else:
            score += 10; verified.append("Your verified degree meets the stated academic requirement.")
    else:
        uncertain = True; inferred.append("The academic requirement needs verification.")
    countries = req.get("countries") or []
    country = profile.get("country", "")
    if countries:
        if "country" not in fields or not country:
            uncertain = True; reasons.append("Confirm your country of residence.")
        elif country.casefold() not in {c.casefold() for c in countries} or any(country.casefold() not in {c.casefold() for c in group} for group in req.get("country_groups", [])):
            rejection = True; reasons.append(f"The role explicitly requires residence in {' / '.join(countries)}.")
        else:
            verified.append(f"Your country meets the explicit geographic requirement ({country})."); score += 10
    else:
        # Office/remote location does not prove authorization or worldwide remote work.
        uncertain = True
        inferred.append(f"Listed location: {job.get('location') or 'unspecified'}; geographic and work-authorization eligibility require review.")
    if req.get("work_authorization"):
        # Generic authorization claims are legally significant. Require exact verified policy fact.
        requirements_text = req["work_authorization"]
        explicit_answers = profile.get("verified_answers") or {}
        answer = explicit_answers.get(requirements_text)
        if not answer or not isinstance(answer, dict) or answer.get("verified") is not True:
            uncertain = True; reasons.append("Work authorization, citizenship, visa, or clearance question requires human review.")
        elif answer.get("eligible") is False:
            rejection = True; reasons.append("Your verified authorization answer does not meet this role's requirement.")
        elif answer.get("eligible") is True:
            verified.append("A verified answer exists for the exact stated authorization requirement.")
        else:
            uncertain = True; reasons.append("The verified authorization answer does not explicitly establish eligibility; human review is required.")
    experience = req.get("min_experience_years")
    if experience is not None and experience > 0:
        years_experience = profile.get("experience_years")
        if "experience_years" not in fields or not isinstance(years_experience, (int, float)) or isinstance(years_experience, bool) or not math.isfinite(years_experience) or years_experience < 0:
            uncertain = True; reasons.append(f"Verify the stated {experience}-year experience requirement.")
        elif years_experience < experience:
            rejection = True; reasons.append(f"Requires {experience} years of experience; verified profile has {years_experience}.")
        else:
            verified.append("Your verified experience meets the stated minimum.")
    candidate_skills = {str(s).casefold(): str(s) for s in profile.get("skills", [])} if "skills" in fields else {}
    for group in req.get("required_skill_groups") or []:
        if not any(str(skill).casefold() in candidate_skills for skill in group):
            uncertain = True
            reasons.append("Verify required technical proficiency: " + " or ".join(str(skill) for skill in group))
    job_skills = job.get("skills") or req.get("skills") or []
    overlap = sorted({candidate_skills[str(s).casefold()] for s in job_skills if str(s).casefold() in candidate_skills})
    if job_skills:
        score += round(20 * len(overlap) / len(set(str(s).casefold() for s in job_skills)))
        if overlap: verified.append("Verified skill overlap: " + ", ".join(overlap))
        elif not candidate_skills:
            inferred.append("No verified skills available for comparison.")
    ranking_signals = []
    interests = [str(v) for v in profile.get("interests", [])]
    if any(_interest_match(interest, job) for interest in interests):
        score += 5; ranking_signals.append("Matches a selected technical interest (+5).")
    company = str(job.get("company", "")).casefold().strip()
    if company and company in {str(value).casefold().strip() for value in profile.get("preferred_employers", [])}:
        score += 3; ranking_signals.append("Preferred employer (+3).")
    if profile.get("remote_preferred") is True and job.get("remote") is True:
        score += 2; ranking_signals.append("Matches remote-work preference (+2).")
    location = str(job.get("location", "")).casefold()
    locations = [str(value).casefold().strip() for value in profile.get("preferred_locations", [])]
    if any(value and (bool(re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", location)) or value == "remote" and job.get("remote") is True) for value in locations):
        score += 2; ranking_signals.append("Matches a preferred location (+2).")
    if profile.get("paid_preferred") is True and _disclosed_paid(job.get("compensation")):
        score += 2; ranking_signals.append("Disclosed paid compensation matches preference (+2).")
    published = _parse_date(job.get("published_at"))
    if published and 0 <= (now - published).total_seconds() <= 72*3600: score += 5
    if not job.get("description"):
        uncertain = True; reasons.append("The full job description is unavailable.")
    # External requirement dictionaries may come from connectors or operator configuration.
    # Validate their evidence before trusting asserted hard requirements.
    if not req.get("evidence"):
        uncertain = True; inferred.append("Requirement evidence is unavailable; review the official posting.")
    eligibility = "ineligible" if rejection else ("review" if uncertain else "eligible")
    if rejection: score = min(score, 24)
    if not reasons:
        reasons.append("Verified requirements match your profile." if eligibility == "eligible" else "Review missing eligibility information before applying.")
    return {"score": max(0, min(100, score)), "eligibility": eligibility,
            "reasons": reasons, "verified": verified, "inferred": inferred, "skill_overlap": overlap, "ranking_signals": ranking_signals}
