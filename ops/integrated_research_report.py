"""Integrated fail-closed research diagnostics for archived football predictions."""
import argparse
import json
from pathlib import Path
from sealed_ft_candidate_linkage import link
from settlement_gap import settlement_gap
from ev_screen import screen_ev

def build_report(sealed, diagnostic, verified_count=0, odds=None, probability=None, calibrated=False, fresh_odds=False):
    linkage=link(sealed,diagnostic)
    coverage=settlement_gap(verified_count)
    ev_result = None
    if odds is not None and probability is not None:
        ev_result = screen_ev(odds, probability, calibrated=calibrated, fresh_odds=fresh_odds)
    return {
        "ev_screen": ev_result,
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
    parser.add_argument("--odds",type=float)
    parser.add_argument("--probability",type=float)
    parser.add_argument("--calibrated",action="store_true")
    parser.add_argument("--fresh-odds",action="store_true")
    args=parser.parse_args()
    sealed=json.loads(Path(args.sealed).read_text(encoding="utf-8"))
    diagnostic=json.loads(Path(args.diagnostic).read_text(encoding="utf-8"))
    report=build_report(sealed,diagnostic,args.verified_count,
                        odds=args.odds,probability=args.probability,
                        calibrated=args.calibrated,fresh_odds=args.fresh_odds)
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Research readiness:",report["settlement_coverage"]["remaining"],"settlements remaining")

if __name__=="__main__":
    main()
