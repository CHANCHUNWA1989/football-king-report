"""Export genuine, validated pre-kickoff paired archives for later FT consensus.

No historical outcome is used. Only archive records passing the existing
forward_validation.load_archived gate are exported. Fixture identifiers are
stable canonical JSON strings and MUST be used by independent FT collectors.
"""
import argparse
import json
from pathlib import Path
from forward_validation import load_archived
from source_fixture_identity import identity_metadata

def export_archives(root):
    rows=[]
    for key, record in load_archived(root):
        rows.append({
            "fixture_id":json.dumps(key,ensure_ascii=False,separators=(",",":")),
            "league":key[0],"home":record["home"],"away":record["away"],
            "kickoff_utc":record["kickoff_utc"],
            "sealed_at_utc":record["prediction_utc"],
            "market_snapshot_utc":record["market_snapshot_utc"],
            "model":record["model"],"market":record["market"],
            **identity_metadata(record),
            "independently_verified":False,"eligible_for_model_scoring":False,
            "production_recommendations":"DISABLED"
        })
    return rows

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--archives",default="research_pairs")
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(export_archives(args.archives),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
