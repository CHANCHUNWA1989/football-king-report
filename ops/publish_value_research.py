"""Publish a fail-closed EV status artifact without fabricating market quotes."""
import argparse
import json
from pathlib import Path
from value_research_pipeline import evaluate

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--site",required=True)
    parser.add_argument("--input")
    args=parser.parse_args()
    rows=[]
    if args.input:
        rows=json.loads(Path(args.input).read_text(encoding="utf-8"))
    report=evaluate(rows)
    report["input_status"]="PROVIDED" if args.input else "NO_VERIFIED_MARKET_INPUT"
    report["production_recommendations"]="DISABLED"
    site=Path(args.site)
    site.mkdir(parents=True,exist_ok=True)
    (site/"value_research.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
