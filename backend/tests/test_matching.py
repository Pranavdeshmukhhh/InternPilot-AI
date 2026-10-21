from datetime import datetime, timedelta, timezone

import pytest

from app.matching import evaluate, extract_requirements, plain_text


PROFILE = {"country": "India", "graduation_year": 2029, "degree": "B.Tech Computer Science",
           "skills": ["Python", "SQL"], "interests": ["software"],
           "verified_fields": ["country", "graduation_year", "degree", "skills"]}


def posting(text, **kwargs):
    return {"title": "Software Engineer Intern", "location": "India", "description": text,
            "requirements": extract_requirements(text, location="India"), **kwargs}


ELIGIBLE = "Currently pursuing a Bachelor's degree, graduating in 2029. Must be based in India. Python and SQL."


def test_explicit_2029_verified_match():
    result = evaluate(posting(ELIGIBLE), PROFILE)
    assert result["eligibility"] == "eligible"
    assert result["skill_overlap"] == ["Python", "SQL"]
    assert result["score"] >= 80


def test_explicit_wrong_graduation_rejected():
    result = evaluate(posting(ELIGIBLE.replace("2029", "2027 or 2028")), PROFILE)
    assert result["eligibility"] == "ineligible"
    assert result["score"] <= 24
    assert any("2029" in reason for reason in result["reasons"])


@pytest.mark.parametrize("wording,expected", [
    ("Expected graduation between 2028 and 2030", [2028, 2029, 2030]),
    ("Graduating in 2028–2030", [2028, 2029, 2030]),
    ("2028 or 2029 graduates", [2028, 2029]),
    ("2028–2030 graduates", [2028, 2029, 2030]),
    ("2028 to 2030 graduates", [2028, 2029, 2030]),
    ("Expected graduation 2029", [2029]),
])
def test_graduation_range_and_leading_years(wording, expected):
    req = extract_requirements(wording)
    assert req["graduation_years"] == expected
    assert req["evidence"][0]["quote"] == wording


@pytest.mark.parametrize("wording,key,value", [
    ("Graduating in 2028 or later", "graduation_min", 2028),
    ("Graduating in 2028 or earlier", "graduation_max", 2028),
    ("Graduation before 2029", "graduation_max", 2028),
    ("Graduation after 2029", "graduation_min", 2030),
    ("Graduation later than 2029", "graduation_min", 2030),
    ("Graduation prior to 2029", "graduation_max", 2028),
])
def test_graduation_open_bounds(wording, key, value):
    assert extract_requirements(wording)[key] == value


@pytest.mark.parametrize("wording", [
    "Graduation after 2027 and before 2030",
    "Graduation no earlier than 2028 and no later than 2029",
    "Graduation in 2028 or later, but no later than 2029",
])
def test_combined_graduation_bounds_preserve_both_limits(wording):
    text = "Currently pursuing a Bachelor's degree. Must be based in India. " + wording
    job = posting(text)
    assert job["requirements"]["graduation_min"] == 2028
    assert job["requirements"]["graduation_max"] == 2029
    assert evaluate(job, PROFILE)["eligibility"] == "eligible"
    assert evaluate(job, {**PROFILE, "graduation_year": 2030})["eligibility"] == "ineligible"
    assert evaluate(job, {**PROFILE, "graduation_year": 2027})["eligibility"] == "ineligible"


@pytest.mark.parametrize("wording", ["Graduation after May 2029", "Graduation before December 2029", "Graduation prior to June 2029"])
def test_month_boundary_never_rejects_a_matching_year_without_month_evidence(wording):
    text = "Currently pursuing a Bachelor's degree. Must be based in India. " + wording
    assert evaluate(posting(text), PROFILE)["eligibility"] == "review"


@pytest.mark.parametrize("wording", ["Graduation before 2028 or after 2030", "Graduation in 2028 or later, or before 2026"])
def test_alternative_graduation_windows_are_not_combined_into_and_bounds(wording):
    text = "Currently pursuing a Bachelor's degree. Must be based in India. " + wording
    job = posting(text)
    assert job["requirements"]["graduation_min"] is None
    assert job["requirements"]["graduation_max"] is None
    assert evaluate(job, {**PROFILE, "graduation_year": 2032})["eligibility"] == "review"


def test_summer_program_year_not_graduation_requirement():
    req = extract_requirements("Summer 2027 software internship. Currently pursuing a Bachelor's degree.")
    assert req["graduation_years"] == []
    assert evaluate(posting("Summer 2027 software internship. Currently pursuing a Bachelor's degree. Must be based in India."), PROFILE)["eligibility"] == "review"


def test_remote_does_not_imply_worldwide_eligibility():
    role = posting("Currently pursuing a Bachelor's degree, graduating 2029. Remote role.", remote=True)
    assert evaluate(role, PROFILE)["eligibility"] == "review"


def test_explicit_wrong_country_rejected():
    assert evaluate(posting(ELIGIBLE.replace("India", "United States")), PROFILE)["eligibility"] == "ineligible"


def test_unverified_profile_does_not_gain_eligibility():
    assert evaluate(posting(ELIGIBLE), {**PROFILE, "verified_fields": []})["eligibility"] == "review"


def test_sensitive_authorization_pauses_even_if_country_matches():
    job = posting(ELIGIBLE + " Must be legally authorized to work in India without visa sponsorship.")
    assert evaluate(job, PROFILE)["eligibility"] == "review"
    requirement = job["requirements"]["work_authorization"]
    profile = {**PROFILE, "verified_answers": {requirement: {"verified": True, "eligible": True}}}
    assert evaluate(job, profile)["eligibility"] == "eligible"
    profile["verified_answers"][requirement]["eligible"] = False
    assert evaluate(job, profile)["eligibility"] == "ineligible"


def test_phd_required_rejects_undergraduate():
    job = posting(ELIGIBLE.replace("Bachelor's", "PhD"))
    assert evaluate(job, PROFILE)["eligibility"] == "ineligible"


def test_preferred_phd_is_not_hard_requirement():
    job = posting(ELIGIBLE + " A PhD is preferred.")
    assert job["requirements"]["degree_levels"] == ["undergraduate"]
    assert evaluate(job, PROFILE)["eligibility"] == "eligible"


def test_experience_missing_review_and_insufficient_reject():
    job = posting(ELIGIBLE + " Requires 2 years of professional experience.")
    assert evaluate(job, PROFILE)["eligibility"] == "review"
    p = {**PROFILE, "experience_years": 0, "verified_fields": [*PROFILE["verified_fields"], "experience_years"]}
    assert evaluate(job, p)["eligibility"] == "ineligible"


def test_expired_deadline_rejected_and_bad_date_safe():
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert evaluate(posting(ELIGIBLE, deadline=expired), PROFILE)["eligibility"] == "ineligible"
    assert evaluate(posting(ELIGIBLE, deadline="unknown"), PROFILE)["eligibility"] == "eligible"


def test_html_hidden_content_not_evidence():
    text = plain_text('<p>Must be based in India.</p><script>Graduating 2029</script><style>PhD required</style>')
    assert "Graduating" not in text
    assert extract_requirements(text)["graduation_years"] == []


def test_preferred_graduation_does_not_reject_candidate():
    job = posting("Bachelor's degree required. Must be based in India. Expected graduation 2027 preferred.")
    assert job["requirements"]["graduation_years"] == []
    assert job["requirements"]["preferences"]
    assert evaluate(job, PROFILE)["eligibility"] == "review"


@pytest.mark.parametrize("wording,key", [("Graduating no earlier than June 2029", "graduation_min"), ("Graduating by August 2029", "graduation_max"), ("Graduating not before 2029", "graduation_min")])
def test_graduation_boundary_phrasing(wording, key):
    assert extract_requirements(wording)[key] == 2029


def test_experience_range_uses_minimum():
    assert extract_requirements("2-3 years of relevant experience required")["min_experience_years"] == 2


@pytest.mark.parametrize("experience", [True, False, float("nan"), float("inf"), float("-inf"), -1])
def test_invalid_experience_value_cannot_establish_verified_eligibility(experience):
    profile = {**PROFILE, "experience_years": experience, "verified_fields": [*PROFILE["verified_fields"], "experience_years"]}
    assert evaluate(posting(ELIGIBLE + " Requires 1 year of experience."), profile)["eligibility"] == "review"


def test_all_legal_requirements_preserved_not_only_last_sentence():
    req = extract_requirements("U.S. citizenship. Active security clearance. Authorization to work in the United States.")
    assert req["work_authorization"].count("\n") == 2
    assert len([v for v in req["evidence"] if v["field"] == "work_authorization"]) == 3


@pytest.mark.parametrize("eligible", [None, "yes", "true", 1, {}, []])
def test_authorization_requires_explicit_boolean_true(eligible):
    job = posting(ELIGIBLE + " Must be legally authorized to work in India.")
    requirement = job["requirements"]["work_authorization"]
    profile = {**PROFILE, "verified_answers": {requirement: {"verified": True, "eligible": eligible}}}
    assert evaluate(job, profile)["eligibility"] == "review"


def test_verified_authorization_without_eligibility_answer_requires_review():
    job = posting(ELIGIBLE + " Must be legally authorized to work in India.")
    requirement = job["requirements"]["work_authorization"]
    profile = {**PROFILE, "verified_answers": {requirement: {"verified": True}}}
    assert evaluate(job, profile)["eligibility"] == "review"


def test_negated_graduation_eligibility_rejected():
    job = posting(ELIGIBLE + " Students graduating in 2029 are not eligible.")
    result = evaluate(job, PROFILE)
    assert result["eligibility"] == "ineligible"
    assert job["requirements"]["excluded_graduation_years"] == [2029]
    assert any("excluded" in value for value in result["reasons"])


def test_negated_country_eligibility_rejected():
    job = posting(ELIGIBLE + " Candidates must not be based in India.")
    assert evaluate(job, PROFILE)["eligibility"] == "ineligible"
    assert job["requirements"]["excluded_countries"] == ["India"]


def test_separate_mandatory_degree_clauses_are_not_or_union():
    job = posting(ELIGIBLE + " A PhD is required.")
    assert job["requirements"]["degree_groups"] == [["undergraduate"], ["phd"]]
    assert evaluate(job, PROFILE)["eligibility"] == "ineligible"


def test_alternative_degrees_within_one_clause_remain_alternatives():
    job = posting(ELIGIBLE.replace("Bachelor's degree", "Bachelor's or Master's degree"))
    assert job["requirements"]["degree_groups"] == [["undergraduate", "masters"]]
    assert evaluate(job, PROFILE)["eligibility"] == "eligible"


@pytest.mark.parametrize("clause", [
    "You must have a GPA of at least 3.5.",
    "At least 75% marks required.",
    "Candidates must be in their second year.",
    "A degree in Computer Science is required.",
    "You must be available full-time for six months.",
    "Candidates must be at least age 18.",
    "You must be willing to relocate.",
])
def test_unsupported_mandatory_detail_forces_review(clause):
    job = posting(ELIGIBLE + " " + clause)
    assert job["requirements"]["uncertain"]
    assert evaluate(job, PROFILE)["eligibility"] == "review"


def test_explicit_extractor_uncertainty_is_never_ignored():
    job = posting(ELIGIBLE)
    job["requirements"]["uncertain"] = ["Special university enrollment condition requires review."]
    assert evaluate(job, PROFILE)["eligibility"] == "review"


def test_grad_year_cannot_be_confused_with_later_internship_start_year():
    job = posting("Currently pursuing a Bachelor's degree. Must graduate in 2028 and be available for summer 2029. Must be based in India.")
    assert job["requirements"]["graduation_years"] == [2028]
    assert evaluate(job, PROFILE)["eligibility"] == "ineligible"


def test_leading_graduate_year_does_not_absorb_unrelated_summer_year():
    req = extract_requirements("Summer 2027 internship for 2028 graduates.")
    assert req["graduation_years"] == [2028]


def test_month_specific_graduation_needs_more_than_year_only_profile():
    job = posting(ELIGIBLE.replace("graduating in 2029", "graduating by May 2029"))
    assert evaluate(job, PROFILE)["eligibility"] == "review"


def test_negated_phd_requirement_does_not_become_hard_requirement():
    job = posting(ELIGIBLE + " A PhD is not required.")
    assert job["requirements"]["degree_levels"] == ["undergraduate"]
    assert evaluate(job, PROFILE)["eligibility"] == "review"


def test_missing_required_technical_skill_requires_review():
    profile = {**PROFILE, "skills": ["TypeScript"]}
    job = posting(ELIGIBLE + " Must have Python proficiency.")
    assert evaluate(job, profile)["eligibility"] == "review"
    assert evaluate(job, PROFILE)["eligibility"] == "eligible"


def test_preferred_skill_does_not_become_mandatory():
    profile = {**PROFILE, "skills": ["TypeScript"]}
    assert evaluate(posting(ELIGIBLE + " Python proficiency is preferred."), profile)["eligibility"] == "eligible"


def test_required_skill_alternatives_and_conjunctions():
    either = posting(ELIGIBLE + " Must have Python or Java proficiency.")
    both = posting(ELIGIBLE + " Must have Python and Java proficiency.")
    assert evaluate(either, PROFILE)["eligibility"] == "eligible"
    assert evaluate(both, PROFILE)["eligibility"] == "review"


def test_mixed_skill_condition_is_not_silently_assumed_or():
    job = posting(ELIGIBLE + " Must have Java and Python or Rust proficiency.")
    assert evaluate(job, PROFILE)["eligibility"] == "review"


def test_unparsed_mandatory_condition_requires_review():
    job = posting(ELIGIBLE + " Candidates must hold an industry certification.")
    assert evaluate(job, PROFILE)["eligibility"] == "review"


def test_no_prior_experience_statement_does_not_create_unknown_mandate():
    assert evaluate(posting(ELIGIBLE + " No prior experience required."), PROFILE)["eligibility"] == "eligible"


def test_separate_mandatory_geographic_clauses_are_not_unioned():
    job = posting(ELIGIBLE + " Must be based in the United States.")
    assert evaluate(job, PROFILE)["eligibility"] == "ineligible"


def test_separate_mandatory_graduation_clauses_are_not_unioned():
    job = posting(ELIGIBLE + " Graduation in 2027 required.")
    assert evaluate(job, PROFILE)["eligibility"] == "ineligible"


def test_preferred_geography_does_not_become_mandatory():
    assert evaluate(posting(ELIGIBLE + " Candidates based in the United States only preferred."), PROFILE)["eligibility"] == "eligible"


def test_editing_employer_preference_changes_ranking():
    base = posting(ELIGIBLE, company="NVIDIA")
    profile = {**PROFILE, "skills": [], "interests": []}
    before = evaluate(base, profile)
    after = evaluate(base, {**profile, "preferred_employers": ["NVIDIA"]})
    assert after["score"] == before["score"] + 3
    assert after["eligibility"] == before["eligibility"] == "eligible"


def test_remote_location_and_paid_preferences_are_live_ranking_inputs():
    role = posting(ELIGIBLE, remote=True, compensation="INR 25000 / month")
    profile = {**PROFILE, "skills": [], "interests": [], "remote_preferred": False, "paid_preferred": False, "preferred_locations": []}
    original = evaluate(role, profile)["score"]
    assert evaluate(role, {**profile, "remote_preferred": True})["score"] == original + 2
    assert evaluate(role, {**profile, "paid_preferred": True})["score"] == original + 2
    assert evaluate(role, {**profile, "preferred_locations": ["India"]})["score"] == original + 2
    assert evaluate(role, {**profile, "remote_preferred": True, "paid_preferred": True, "preferred_locations": ["Remote"]})["score"] == original + 6


@pytest.mark.parametrize("compensation", [None, "", "Unpaid", "No stipend", "Competitive", "USD 0", "USD 0 (2029 cohort)", "Stipend TBD", "Stipend not disclosed", "May be paid", "Paid depending on funding", '{"paid":false}', '{"currency":"USD","min":0,"max":0}'])
def test_unknown_unpaid_or_zero_compensation_does_not_receive_paid_bonus(compensation):
    role = posting(ELIGIBLE, compensation=compensation)
    profile = {**PROFILE, "skills": [], "interests": [], "paid_preferred": False}
    assert evaluate(role, {**profile, "paid_preferred": True})["score"] == evaluate(role, profile)["score"]


def test_disclosed_positive_json_compensation_receives_paid_bonus():
    role = posting(ELIGIBLE, compensation='{"currency":"USD","min":0,"max":3000}')
    profile = {**PROFILE, "skills": [], "interests": []}
    assert evaluate(role, {**profile, "paid_preferred": True})["score"] == evaluate(role, profile)["score"] + 2


@pytest.mark.parametrize("compensation", ["Paid internship", "INR 25000 per month", "25000 INR per month", "USD 0–3000 per month", "INR 0 to 25000"])
def test_explicit_positive_pay_receives_paid_bonus(compensation):
    role = posting(ELIGIBLE, compensation=compensation)
    profile = {**PROFILE, "skills": [], "interests": []}
    assert evaluate(role, {**profile, "paid_preferred": True})["score"] == evaluate(role, profile)["score"] + 2


@pytest.mark.parametrize("interest,title", [("Software engineering", "Software Engineer Intern"), ("AI/ML", "Machine Learning Intern"), ("Cloud computing", "Cloud Engineer Intern"), ("Web development", "Frontend Developer Intern")])
def test_technical_interest_aliases_match_real_title_wording(interest, title):
    role = posting(ELIGIBLE)
    role["title"] = title
    profile = {**PROFILE, "skills": [], "interests": []}
    assert evaluate(role, {**profile, "interests": [interest]})["score"] == evaluate(role, profile)["score"] + 5
