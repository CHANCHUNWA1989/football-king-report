"""Integrated fail-closed research diagnostics for archived football predictions."""
import argparse
import json
from pathlib import Path
from sealed_ft_candidate_linkage import link
from settlement_gap import settlement_gap

def build_report(sealed, diagnostic, verified_count=0):
    linkage=link(sealed,diagnostic)
    coverage=settlement_gap(verified_count)
    return {
        "schema":"football-king-integrated-research-v1",
        "status":"RESEARCH_ONLY",
        "archive_rows":linkage["archive_fixture_count"],
        "unique_fixture_ids":linkage["unique_archive_fixture_count"],
        "identity_conflicts":linkage["conflicting_fixture_id_count"],
        "candidate_links":linkage["candidate_link_count"],
        "candidate_provenance_counts":linkage["candidate_provenance_counts"],
        "link_blockers":linkage["link_blockers"],
        "settlement_coverage":coverage,
        "eligible_for_model_scoring":False,
        "production_recommendations":"DISABLED",
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sealed",required=True)
    parser.add_argument("--diagnostic",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--verified-count",type=int,default=0)
    args=parser.parse_args()
    sealed=json.loads(Path(args.sealed).read_text(encoding="utf-8"))
    diagnostic=json.loads(Path(args.diagnostic).read_text(encoding="utf-8"))
    report=build_report(sealed,diagnostic,args.verified_count)
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Research readiness:",report["settlement_coverage"]["remaining"],"settlements remaining")

if __name__=="__main__":
    main()
