"""Search breadth is bounded, factual and independent of employer popularity."""
from app.regional_search import MAX_SEARCH_SOURCES, search_freshness, search_sources
from app.schemas import SourceInput


def test_default_lanes_find_small_employers_and_nonstandard_student_titles():
    sources = search_sources()
    queries = " ".join(source["slug"] for source in sources)
    for term in ("startup", "incubator", "technology park", "project intern", "student developer",
                 "graduate trainee", "research assistant", "summer student", "university"):
        assert term in queries
    assert not any("site:linkedin.com" in source["slug"] for source in sources)
    for source in sources:
        SourceInput(**source)
        assert len(source["slug"]) <= 200
        assert source["interval_seconds"] >= 21600
    assert len({source["slug"] for source in sources}) == len(sources)


def test_remote_india_international_and_local_have_distinct_lanes():
    sources = search_sources()
    for region in ("Nagpur", "Pune", "India", "Remote", "International"):
        for kind in ("internship", "hackathon"):
            assert any(source["company"] == f"{region} {kind} search" for source in sources)
    assert all("location" not in source and "eligibility" not in source for source in sources)


def test_many_cities_are_bounded_and_each_gets_basic_opportunity_lanes():
    cities = [f"City {index}" for index in range(20)]
    sources = search_sources({"preferred_local_cities": cities})
    assert len(sources) == MAX_SEARCH_SOURCES
    for city in cities:
        for kind in ("internship", "hackathon"):
            assert any(source["company"] == f"{city} {kind} search" for source in sources)
    assert any(source["company"] == "Remote internship search" for source in sources)


def test_no_local_selection_keeps_national_remote_and_international_discovery():
    sources = search_sources({"preferred_local_cities": []})
    assert len(sources) == 8
    assert not any("Pune" in source["slug"] or "Nagpur" in source["slug"] for source in sources)


def test_local_input_is_bounded_quoted_and_deduplicated():
    sources = search_sources({"preferred_local_cities": [" Mumbai ", "mumbai", 'City" ) OR site:blocked.test ('],
                              "include_nearby_locations": False})
    assert len([source for source in sources if source["company"] == "Mumbai internship search"]) == 1
    assert any('("Mumbai")' in source["slug"] for source in sources)
    assert not any("site:" in source["slug"] for source in sources)
    long_city = search_sources({"preferred_local_cities": ["A" * 100]})
    assert len(long_city) == 14 and all(len(source["slug"]) <= 200 for source in long_city)


def test_durable_employer_directories_are_not_hidden_by_freshness_filters():
    for source in search_sources():
        expected = None if "employer discovery" in source["company"] else "pm" if "research programs" in source["company"] else "pw"
        assert search_freshness(source) == expected
    assert search_freshness({}) == "pw"
