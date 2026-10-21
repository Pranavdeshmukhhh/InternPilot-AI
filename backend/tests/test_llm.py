import asyncio
import json

import httpx
import pytest

from app.llm import _validate_base_url, analyze_job, analyze_requirements, annotate_jobs


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr("app.llm.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))])


def run(coroutine):
    return asyncio.run(coroutine)


def test_disabled_provider_makes_no_request():
    result = run(analyze_requirements("Python", provider="disabled"))
    assert result["status"] == "disabled"
    assert result["requirements"] == []
    assert result["verified"] is False


def test_structured_response_requires_exact_evidence_and_never_marks_verified(public_dns):
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        content = {
            "summary": "A student internship.",
            "requirements": [
                {"kind": "graduation_year", "value": "2029", "evidence": "Expected graduation in 2029", "uncertain": False},
                {"kind": "skill", "value": "Invented skill", "evidence": "NO_SUCH_EVIDENCE", "uncertain": False},
            ],
            "warnings": [],
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await analyze_requirements("Expected graduation in 2029. Python required.", provider="openai_compatible", api_key="secret-test-key", model="test-model", base_url="https://llm.example/v1", client=client)
    result = run(scenario())
    assert result["status"] == "available"
    assert len(result["requirements"]) == 1
    assert result["requirements"][0]["verified"] is False
    assert result["verified"] is False
    assert any("Discarded 1" in message for message in result["warnings"])
    assert "secret-test-key" not in json.dumps(captured)
    assert captured[0]["response_format"]["type"] == "json_object"


@pytest.mark.parametrize("bad_content", ["not JSON", '{"summary":"x","requirements":[],"warnings":[],"submit":true}', '{"summary":"x","requirements":[{"kind":"graduation_year","value":2029,"evidence":"2029","uncertain":false}],"warnings":[]}'])
def test_invalid_model_output_fails_closed(public_dns, bad_content):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": bad_content}}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await analyze_requirements("2029", provider="openai_compatible", model="test", base_url="https://llm.example", client=client)
    result = run(scenario())
    assert result["status"] == "error"
    assert result["requirements"] == []


def test_provider_failure_does_not_echo_credentials(public_dns):
    def handler(request):
        return httpx.Response(401, text="Authorization: Bearer secret-test-key")
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await analyze_job({"description": "A real role"}, provider="openai_compatible", api_key="secret-test-key", model="test", base_url="https://llm.example", client=client)
    result = run(scenario())
    assert result["status"] == "error"
    assert "secret-test-key" not in json.dumps(result)


@pytest.mark.parametrize("address", ["169.254.169.254", "10.0.0.1", "127.0.0.1", "::1", "192.168.1.2"])
def test_private_llm_urls_blocked_without_explicit_local_permission(monkeypatch, address):
    monkeypatch.setattr("app.llm.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", (address, 443))])
    with pytest.raises(ValueError, match="private"):
        _validate_base_url("https://llm.example/v1", allow_local=False)


def test_explicit_loopback_provider_permission_does_not_allow_other_private_hosts(monkeypatch):
    monkeypatch.setattr("app.llm.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 8000))])
    assert _validate_base_url("http://127.0.0.1:8000/v1", allow_local=True) == "http://127.0.0.1:8000/v1"
    with pytest.raises(ValueError):
        _validate_base_url("http://other.example:8000/v1", allow_local=True)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@llm.example/v1", "https://llm.example/v1?key=secret", "https://llm.example/#fragment", "http://llm.example/v1"])
def test_malformed_or_insecure_base_urls_are_rejected(public_dns, url):
    with pytest.raises(ValueError):
        _validate_base_url(url, allow_local=False)


def test_batch_annotation_preserves_deterministic_requirements_and_reuses_cached_analysis(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "batch-test-model")
    calls = []
    async def analyze(description, **kwargs):
        calls.append(description)
        return {"status": "available", "verified": False, "requirements": [{"kind": "graduation_year", "value": "2029", "evidence": "2029", "verified": False}], "warnings": []}
    monkeypatch.setattr("app.llm.analyze_requirements", analyze)
    monkeypatch.setattr("app.llm._ANALYSIS_CACHE", __import__("collections").OrderedDict())
    original = {"url": "https://jobs.example/1", "description": "Explicit graduation year 2029", "requirements": {"graduation_years": [2029], "uncertain": []}}
    first = run(annotate_jobs([original]))[0]
    second = run(annotate_jobs([original]))[0]
    assert len(calls) == 1
    assert first["requirements"] == original["requirements"]
    assert "llm_analysis" not in original
    assert first["llm_analysis"]["verified"] is False
    assert first["llm_analysis"] == second["llm_analysis"]
    monkeypatch.setattr("app.llm._ANALYSIS_CACHE", __import__("collections").OrderedDict())
    restarted = run(annotate_jobs([original], previous_by_url={original["url"]: first}))[0]
    assert len(calls) == 1
    assert restarted["llm_analysis"] == first["llm_analysis"]
    changed = {**original, "description": "Graduating in 2028"}
    run(annotate_jobs([changed], previous_by_url={original["url"]: first}))
    assert len(calls) == 2


def test_batch_disabled_annotation_has_no_provider_side_effect(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "disabled")
    original = {"description": "A student role", "requirements": {"unknown": True}}
    result = run(annotate_jobs([original]))[0]
    assert result["llm_analysis"]["status"] == "disabled"
    assert result["requirements"] == {"unknown": True}
    assert "llm_analysis" not in original
