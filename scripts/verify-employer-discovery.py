"""Read-only publisher-page verification; no accounts or applications are used."""
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.discovery import discover


async def main():
    source = {"kind": "html", "url": "https://www.sarvam.ai/careers",
              "company": "Sarvam AI public career page", "permitted": True}
    report = {"at": datetime.now(UTC).isoformat(), "read_only": True,
              "publisher_url": source["url"], "search_provider_tested": False,
              "external_submissions": 0, "sources_enabled": 0,
              "note": "A publisher snapshot, not a guarantee of availability, undergraduate eligibility or employer size."}
    try:
        result = await discover(source)
        report.update(responded=True, records_received=len(result["jobs"]),
                      opportunities=[{key: job.get(key) for key in ("title", "url", "location", "verification_status", "application_url_verified")} for job in result["jobs"]],
                      source_candidates=[{key: item.get(key) for key in ("kind", "slug", "url", "evidence_url", "verified")} for item in result["cache"].get("source_candidates", [])],
                      complete_inventory=not result["cache"].get("truncated", False))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        report.update(responded=False, error_type=type(exc).__name__)
    output = ROOT / "artifacts" / "employer-discovery-live.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["responded"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
