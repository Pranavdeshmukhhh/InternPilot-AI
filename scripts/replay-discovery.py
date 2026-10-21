#!/usr/bin/env python3
"""Read-only, offline eligibility replay of a dated public listing snapshot.

This command does not discover new listings, modify the database, or apply to jobs.
For live discovery use the app's Sources / Run discovery action.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.matching import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "artifacts" / "live-listings.json")
    parser.add_argument("--profile", type=Path, help="Optional local verified profile JSON; never uploaded")
    parser.add_argument("--output", type=Path, help="Write the report to this local JSON file")
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if snapshot.get("is_snapshot") is not True or not snapshot.get("captured_at"):
        parser.error("Input must be a labeled InternPilot public-listing snapshot.")
    profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile else {
        "country": "India", "graduation_year": 2029, "skills": [],
        "verified_fields": ["country", "graduation_year"],
    }
    evaluated = [{"title": job["title"], "company": job["company"], "url": job["url"],
                  **evaluate(job, profile)} for job in snapshot["jobs"]]
    report = {
        "is_snapshot_replay": True,
        "snapshot_captured_at": snapshot["captured_at"],
        "notice": "Offline historical replay. Availability and requirements may have changed; no live requests or applications are made.",
        "listings": len(evaluated),
        "eligibility_counts": dict(Counter(job["eligibility"] for job in evaluated)),
        "ranked_results": sorted(evaluated, key=lambda job: job["score"], reverse=True),
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Saved offline snapshot replay to {args.output}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
