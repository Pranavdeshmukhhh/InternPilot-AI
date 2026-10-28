"""Read-only verification of current default source geography. No applications."""
import asyncio
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.discovery import default_sources, discover
from app.geography import classify


async def main(production=False):
    async def check(source):
        try:
            result = await discover(source)
            counts = {}
            examples = []
            current = datetime.now(UTC)
            for job in result["jobs"]:
                date = job.get("deadline") or job.get("ends_at")
                if date:
                    try:
                        parsed = datetime.fromisoformat(date)
                        if parsed.tzinfo and parsed<=current:
                            continue
                    except ValueError:
                        pass
                geography = classify(job,{})
                for region in geography["regions"]:
                    counts[region] = counts.get(region,0)+1
                if len(examples)<3:
                    examples.append({"title":job["title"],"location":job.get("location"),"url":job["url"],"regions":geography["regions"],"verification_status":job.get("verification_status","source_response")})
            return {"source":source["company"],"kind":source["kind"],"responded":True,"records_received":len(result["jobs"]),"nonexpired_region_counts":counts,"examples":examples}
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
            return {"source":source["company"],"kind":source["kind"],"responded":False,"error_type":type(exc).__name__}
    kinds={"greenhouse","mlh","internscan","ashby","lever"} if production else {"greenhouse","mlh","internscan"}
    sources = [source for source in default_sources() if source["kind"] in kinds]
    report = {"at":datetime.now(UTC).isoformat(),"read_only":True,"brave_search_tested":False,
              "note":"Region membership is location metadata, not Indian-student eligibility. Source availability can change.",
              "sources":await asyncio.gather(*(check(source) for source in sources)),"external_submissions":0}
    target="production-live-sources.json" if production else "regional-live-sources.json"
    (ROOT/"artifacts"/target).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--production",action="store_true")
    arguments=parser.parse_args()
    asyncio.run(main(arguments.production))
