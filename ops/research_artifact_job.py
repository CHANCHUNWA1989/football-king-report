"""Run the offline provider pipeline using an export path, with an explicit
run-time timestamp. This is for GitHub Actions artifact generation; no API
fetching, recommendations, notifications, or wagering are performed.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from ops.provider_research_cli import run

def main():
    parser = argparse.ArgumentParser(description="Research-only export report artifact")
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    now = datetime.now(timezone.utc).isoformat()
    target = Path(args.outdir)
    report = run(args.input, target / "report.json", target / "report.md",
                 generated_utc=now)
    metadata = {
        "generated_utc": now,
        "fixture_count": report["sample_count"],
        "research_only": True,
        "source_independently_verified": False,
        "positive_ev_verified": False,
        "production_recommendations": "HOLD",
        "automated_betting": "DISABLED",
        "source_input": Path(args.input).name
    }
    (target / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"Research artifacts generated; fixtures={report['sample_count']}; HOLD")

if __name__ == "__main__":
    main()
