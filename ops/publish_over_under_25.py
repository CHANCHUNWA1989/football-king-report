"""Publish evidence-gated OU2.5 daily report, never fabricated recommendations."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from total_goals_evidence import assess

def publish(site, input_path=None, now_utc=None):
    rows=json.loads(Path(input_path).read_text(encoding="utf-8")) if input_path else []
    now=now_utc or datetime.now(timezone.utc).isoformat()
    report=assess(rows,now_utc=now)
    report["generated_at_utc"]=now
    report["input_status"]="PROVIDED_UNVERIFIED_UNTIL_EVIDENCE_CHECK" if input_path else "NO_VERIFIED_MARKET_INPUT"
    report["notice"]="Research candidates only. No verified betting recommendation."
    report["missing_requirements"]=([] if input_path else [
        "REAL_PREMATCH_FIXTURE_FEED","TIMESTAMPED_ODDS_FEED",
        "OUT_OF_SAMPLE_CALIBRATED_EXPECTED_GOALS"])
    dest=Path(site)
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"over_under_25.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--site",required=True)
    p.add_argument("--input")
    p.add_argument("--now-utc")
    args=p.parse_args()
    publish(args.site,args.input,args.now_utc)

if __name__=="__main__":
    main()
