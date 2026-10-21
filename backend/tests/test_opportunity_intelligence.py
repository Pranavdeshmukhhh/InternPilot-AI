from datetime import datetime, timedelta, timezone

import pytest

from app.matching import evaluate
from app.opportunity_intelligence import evaluate_opportunity


PROFILE = {
    "country": "India",
    "graduation_year": 2029,
    "degree": "B.Tech Computer Science",
    "skills": ["Python", "SQL"],
    "interests": [],
    "hackathon_interests": ["AI/ML"],
    "verified_fields": ["country", "graduation_year", "degree", "skills"],
}
OPEN = "Open to all participants worldwide."
INTERNSHIP = "Currently pursuing a Bachelor's degree, graduating in 2029. Must be based in India. Python and SQL."


def hackathon(description=OPEN, **values):
    return {
        "opportunity_type": "hackathon",
        "title": "AI Innovation Hackathon",
        "description": description,
        **values,
    }


def future(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


@pytest.mark.parametrize("kind", [None, "internship"])
def test_internship_matching_outputs_are_preserved_with_enrichment(kind):
    data = {"title": "Software Engineer Intern", "description": INTERNSHIP, "location": "India"}
    if kind:
        data["opportunity_type"] = kind
    expected = evaluate(data, PROFILE)
    result = evaluate_opportunity(data, PROFILE)
    for key, value in expected.items():
        assert result[key] == value
    assert result["missing_skills"] == []
    assert result["deadline_urgency"] == "unknown"
    assert result["recommended_action"]


def test_explicit_open_hackathon_does_not_require_unstated_academic_or_work_authorization():
    profile = {"verified_fields": [], "skills": [], "hackathon_interests": []}
    result = evaluate_opportunity(hackathon(), profile)
    assert result["eligibility"] == "eligible"
    assert 0 <= result["score"] <= 100
    assert any("open" in value.lower() or "worldwide" in value.lower() for value in result["verified"])
    assert not any("graduation" in value.lower() or "work authorization" in value.lower() for value in result["inferred"])
    assert isinstance(result["ranking_signals"], list)
    assert result["recommended_action"]


@pytest.mark.parametrize("description,values", [
    ("Build useful software together.", {}),
    ("Remote hackathon with cloud challenges.", {"remote": True, "location": "Remote"}),
    ("Our sponsors operate worldwide. Build cloud projects remotely.", {}),
    ("Not open to all participants worldwide.", {}),
    ("Build useful software together.", {"open_to_all": True, "worldwide": True}),
    ("<p>Build together.</p><script>Open to all participants worldwide.</script>", {}),
])
def test_geography_metadata_or_worldwide_marketing_does_not_establish_open_eligibility(description, values):
    assert evaluate_opportunity(hackathon(description, **values), PROFILE)["eligibility"] == "review"


def test_explicit_country_restriction_rejects_known_incompatible_country():
    result = evaluate_opportunity(hackathon(OPEN + " Participants must reside in the United States."), PROFILE)
    assert result["eligibility"] == "ineligible"
    assert result["score"] <= 24
    assert result["reasons"]


def test_explicit_country_restriction_requires_verified_country():
    data = hackathon(OPEN + " Participants must reside in India.")
    assert evaluate_opportunity(data, PROFILE)["eligibility"] == "eligible"
    profile = {**PROFILE, "verified_fields": ["graduation_year", "degree", "skills"]}
    assert evaluate_opportunity(data, profile)["eligibility"] == "review"


@pytest.mark.parametrize("requirement", [
    "Participants must graduate in 2028.",
    "A PhD is required.",
])
def test_explicit_incompatible_academic_rules_are_enforced(requirement):
    assert evaluate_opportunity(hackathon(OPEN + " " + requirement), PROFILE)["eligibility"] == "ineligible"


def test_unstated_graduation_is_not_inferred_from_event_year():
    data = hackathon(OPEN + " This is the summer 2027 program.")
    assert evaluate_opportunity(data, PROFILE)["eligibility"] == "eligible"


def test_unknown_mandatory_rule_requires_review_even_with_open_eligibility():
    result = evaluate_opportunity(hackathon(OPEN + " Participants must hold an industry certification."), PROFILE)
    assert result["eligibility"] == "review"
    assert result["reasons"] or result["inferred"]


def test_preferred_qualification_does_not_block_open_hackathon():
    assert evaluate_opportunity(hackathon(OPEN + " A PhD is preferred."), PROFILE)["eligibility"] == "eligible"


def test_age_requirement_uses_only_verified_age():
    data = hackathon(OPEN + " Participants must be at least 18 years old.")
    assert evaluate_opportunity(data, {**PROFILE, "age": 20})["eligibility"] == "review"
    verified = [*PROFILE["verified_fields"], "age"]
    assert evaluate_opportunity(data, {**PROFILE, "age": 17, "verified_fields": verified})["eligibility"] == "ineligible"
    assert evaluate_opportunity(data, {**PROFILE, "age": 20, "verified_fields": verified})["eligibility"] == "eligible"


def test_team_size_requirement_requires_verified_team_size():
    data = hackathon(OPEN + " Team size must be between 2 and 4.")
    assert evaluate_opportunity(data, PROFILE)["eligibility"] == "review"
    assert evaluate_opportunity(data, {**PROFILE, "team_size": 3})["eligibility"] == "review"
    verified = [*PROFILE["verified_fields"], "team_size"]
    assert evaluate_opportunity(data, {**PROFILE, "team_size": 1, "verified_fields": verified})["eligibility"] == "ineligible"
    assert evaluate_opportunity(data, {**PROFILE, "team_size": 3, "verified_fields": verified})["eligibility"] == "eligible"


def test_required_technical_alternatives_are_not_treated_as_conjunctions():
    data = hackathon(OPEN + " Participants must know Python or Rust.")
    assert evaluate_opportunity(data, PROFILE)["eligibility"] == "eligible"
    assert evaluate_opportunity(hackathon(OPEN + " Participants must know Python and Rust."), PROFILE)["eligibility"] == "review"


def test_missing_skills_are_based_on_verified_profile_skills():
    data = hackathon(OPEN + " Build projects in Python and Rust.", skills=["Python", "Rust"])
    result = evaluate_opportunity(data, PROFILE)
    assert result["skill_overlap"] == ["Python"]
    assert result["missing_skills"] == ["Rust"]
    unknown = evaluate_opportunity(data, {**PROFILE, "verified_fields": ["country", "degree", "graduation_year"]})
    assert unknown["skill_overlap"] == []
    assert set(unknown["missing_skills"]) == {"Python", "Rust"}
    assert unknown["score"] < result["score"]


def test_hackathon_interests_change_relevance_without_changing_eligibility():
    data = hackathon()
    without = evaluate_opportunity(data, {**PROFILE, "hackathon_interests": []})
    matching = evaluate_opportunity(data, PROFILE)
    assert matching["score"] > without["score"]
    assert matching["ranking_signals"]
    assert matching["eligibility"] == without["eligibility"] == "eligible"


@pytest.mark.parametrize("delta,expected", [
    ({"hours": 12}, "within_24h"),
    ({"days": 2}, "within_3d"),
    ({"days": 5}, "within_7d"),
    ({"days": 10}, "later"),
    ({"hours": -1}, "expired"),
])
def test_deadline_urgency_uses_actual_explicit_deadline(delta, expected):
    result = evaluate_opportunity(hackathon(deadline=future(**delta)), PROFILE)
    assert result["deadline_urgency"] == expected
    if expected == "expired":
        assert result["eligibility"] == "ineligible"


def test_timezone_offset_deadline_preserves_the_actual_instant():
    deadline = (datetime.now(timezone.utc) + timedelta(hours=12)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert evaluate_opportunity(hackathon(deadline=deadline.isoformat()), PROFILE)["deadline_urgency"] == "within_24h"


@pytest.mark.parametrize("deadline", ["2030-01-02", "2030-01-02T12:00:00", "unknown"])
def test_imprecise_or_invalid_deadlines_do_not_gain_precise_urgency(deadline):
    assert evaluate_opportunity(hackathon(deadline=deadline), PROFILE)["deadline_urgency"] == "unknown"


def test_event_start_is_not_a_registration_or_submission_deadline():
    data = hackathon(starts_at=future(hours=12))
    result = evaluate_opportunity(data, PROFILE)
    assert result["deadline_urgency"] == "unknown"
    assert result["eligibility"] == "eligible"


def test_event_that_has_ended_is_ineligible_even_without_registration_deadline():
    result = evaluate_opportunity(hackathon(ends_at=future(hours=-1)), PROFILE)
    assert result["eligibility"] == "ineligible"


@pytest.mark.parametrize("prize", [None, "", "TBD", "Prizes may be available", "USD 0", "USD 0 (2029 cohort)"])
def test_unknown_conditional_or_zero_prizes_do_not_receive_reward_bonus(prize):
    baseline = evaluate_opportunity(hackathon(), PROFILE)
    result = evaluate_opportunity(hackathon(prizes=prize), PROFILE)
    assert result["score"] == baseline["score"]


def test_positive_prize_requires_evidence_and_does_not_imply_guaranteed_personal_pay():
    baseline = evaluate_opportunity(hackathon(), PROFILE)
    data = hackathon(OPEN + " Total prize pool: USD 1000.", prizes="USD 1000")
    result = evaluate_opportunity(data, PROFILE)
    assert result["score"] > baseline["score"]
    assert result["eligibility"] == "eligible"
    assert not any("guaranteed" in text.lower() for text in result["verified"])


def test_availability_only_applies_when_rules_explicitly_require_attendance():
    start = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=22)).date().isoformat()
    profile = {
        **PROFILE,
        "availability_start": "2035-01-01",
        "availability_end": "2035-02-01",
        "verified_fields": [*PROFILE["verified_fields"], "availability_start", "availability_end"],
    }
    data = hackathon(starts_at=start + "T10:00:00Z", ends_at=end + "T18:00:00Z")
    assert evaluate_opportunity(data, profile)["eligibility"] == "eligible"
    required = hackathon(OPEN + f" Participants must be available from {start} to {end}.", **{
        "starts_at": start + "T10:00:00Z", "ends_at": end + "T18:00:00Z",
    })
    assert evaluate_opportunity(required, PROFILE)["eligibility"] == "review"
    assert evaluate_opportunity(required, profile)["eligibility"] == "ineligible"


def test_llm_advisory_or_unquoted_requirements_cannot_grant_eligibility():
    data = hackathon("Build useful software together.", requirements={"open_to_all": True},
                     advisory={"eligibility": "eligible", "verified": True})
    assert evaluate_opportunity(data, PROFILE)["eligibility"] == "review"
