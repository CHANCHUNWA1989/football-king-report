#!/usr/bin/env python3
"""Research-only provenance and calibration audit. Never enables recommendations."""
import argparse
import json
from pathlib import Path
from scripts.evidence_audit_v2 import audit, timestamp

def review(document, events=None):
    report = audit(document)
    issues = []
    rows = document.get("samples", [])
    strict_verified = 0
    for index, row in enumerate(rows):
        if row.get("fixture_result_source_independently_verified") is True:
            sources = row.get("result_sources")
            if not isinstance(sources, list) or len(sources) < 2:
                issues.append({"index": index, "issue": "two documented result sources required"})
                continue
            ids = set()
            try:
                kickoff = timestamp(row["kickoff_utc"])
                for source in sources:
                    provider = source["upstream_id"]
                    if not provider or not source["url"] or timestamp(source["captured_utc"]) < kickoff:
                        raise ValueError("invalid source provenance")
                    ids.add(provider)
                if len(ids) < 2:
                    raise ValueError("not independent upstreams")
                strict_verified += 1
            except (KeyError, ValueError, TypeError):
                issues.append({"index": index, "issue": "invalid result source provenance"})
    if events is None:
        issues.append({"issue": "direction event history not supplied"})
    else:
        for index, event in enumerate(events):
            try:
                if event["action"] not in ("proposed", "withdrawn", "reversed", "superseded") or not event["fixture_key"]:
                    raise ValueError("invalid event")
                timestamp(event["event_utc"])
            except (KeyError, ValueError, TypeError):
                issues.append({"event_index": index, "issue": "invalid direction event"})
    calibration = {}
    for field in ("p", "m", "ab"):
        group = [row for row in rows if field in row and row.get("y") in (0, 1, 2)]
        if group:
            calibration[field] = {
                "n": len(group),
                "mean_home_probability": sum(row[field][0] for row in group) / len(group),
                "observed_home_rate": sum(row["y"] == 0 for row in group) / len(group),
                "home_top_pick_rate": sum(row[field][0] == max(row[field]) for row in group) / len(group),
            }
    report["strict_verified_count"] = strict_verified
    report["home_calibration_research_only"] = calibration
    report["provenance_and_history_issues"] = issues
    report["promotion_eligible"] = False
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evidence/settled.json")
    parser.add_argument("--events")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    document = json.loads(Path(args.input).read_text(encoding="utf-8"))
    events = json.loads(Path(args.events).read_text(encoding="utf-8")) if args.events else None
    output = json.dumps(review(document, events), indent=2, ensure_ascii=False) + "\n"
    if args.output == "-":
        print(output, end="")
    else:
        Path(args.output).write_text(output, encoding="utf-8")
