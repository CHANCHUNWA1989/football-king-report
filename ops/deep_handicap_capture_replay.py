"""Replay a locally claimed deep-line capture before evaluating result claims.

This is a private in-memory consistency check, not an externally witnessed
archive. It never retrieves data, persists raw quotes or grants forward credit.
"""
import copy
from collections import Counter
from datetime import timedelta
from deep_handicap_private_capture import capture, _time, _digest
from deep_handicap_forward_evaluation import evaluate

MAX_COHORT=200

def _replay_candidate(shadow,quote_report,sealed,as_of):
    if not isinstance(sealed,dict):raise ValueError("INVALID_SEAL")
    original=sealed["candidate"]
    if not isinstance(original,dict) or "results" in original:raise ValueError("INVALID_CANDIDATE")
    recorded=_time(original["evidence"]["recorded_capture_utc"])
    if recorded>as_of or _digest(original)!=sealed.get("candidate_sha256"):
        raise ValueError("CAPTURE_CLOCK_OR_DIGEST")
    replay=capture(shadow,quote_report,now=recorded)
    if replay.get("candidate") is None or replay!=sealed:raise ValueError("CAPTURE_REPLAY")
    return original

def replay_and_evaluate(shadow, quote_report, sealed, results, *, as_of_utc):
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "locally_replayed":False,"external_witness_verified":False,
         "authenticated_forward_samples":0,"positive_ev_verified":False,
         "evaluation":None,"reason":"CAPTURE_REPLAY_REJECTED"}
    try:
        original=_replay_candidate(shadow,quote_report,sealed,_time(as_of_utc))
        if not isinstance(results,list) or not 2<=len(results)<=10:return out
        # Keep original forecasts immutable; settlement is a derived record.
        row=copy.deepcopy(original)
        row["results"]=copy.deepcopy(results)
        report=evaluate([row],as_of_utc=as_of_utc)
        out["locally_replayed"]=True
        out["evaluation"]=report
        n=report["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]["n"]
        out["reason"]="LOCAL_REPLAY_AND_STRUCTURAL_SETTLEMENT" if n==1 else "RESULT_CLAIMS_REJECTED"
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
        return out
    return out


def audit_declared_cohort(entries, *, as_of_utc):
    """Replay every declared local seal, including those without results.

    A caller-supplied roster is not a complete opportunity denominator.
    Reject the entire cohort if any capture or identity is ambiguous; do not
    silently drop it to improve the measured performance. Bounded private
    in-memory research only. No raw inputs or identifiers are returned.
    """
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "declared_roster_reconciled":False,"complete_attempt_denominator_verified":False,
         "selection_bias_ruled_out":False,"external_witness_verified":False,
         "authenticated_forward_samples":0,"positive_ev_verified":False,
         "declared_count":None,"states":None,"evaluation":None,
         "reason":"COHORT_REJECTED"}
    if not isinstance(entries,list) or len(entries)>MAX_COHORT:return out
    out["declared_count"]=len(entries)
    try:
        as_of=_time(as_of_utc)
        seen_fixture=set();seen_market=set();seen_pair=set();digests=[]
        states=Counter();settled=[]
        for item in entries:
            if not isinstance(item,dict) or set(item)!={"shadow","quote_report","sealed","results"}:
                raise ValueError("COHORT_ITEM_SCOPE")
            c=_replay_candidate(item["shadow"],item["quote_report"],item["sealed"],as_of)
            fixture=(c["league_id"],c["fixture_id"])
            market=c["evidence"]["market_event_id"]
            ko=_time(c["kickoff_utc"])
            # Same team pair on the same UTC day under new native IDs is
            # conservatively ambiguous, not an additional independent case.
            pair=(c["league_id"],c["home_id"],c["away_id"],ko.date())
            if fixture in seen_fixture or market in seen_market or pair in seen_pair:
                raise ValueError("COHORT_IDENTITY_DUPLICATE")
            seen_fixture.add(fixture);seen_market.add(market);seen_pair.add(pair)
            digests.append(item["sealed"]["candidate_sha256"])
            claims=item["results"]
            if claims is None:
                states["PENDING_MATURITY" if as_of<ko+timedelta(minutes=105) else "MATURE_WITHOUT_RESULT"]+=1
                continue
            if not isinstance(claims,list) or not 2<=len(claims)<=10:
                states["RESULT_CLAIMS_REJECTED"]+=1
                continue
            row=copy.deepcopy(c);row["results"]=copy.deepcopy(claims)
            check=evaluate([row],as_of_utc=as_of_utc)
            if check["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]["n"]!=1:
                states["RESULT_CLAIMS_REJECTED"]+=1
                continue
            states["SETTLED_LOCAL"]+=1;settled.append(row)
        report=evaluate(settled,as_of_utc=as_of_utc)
        if (sum(states.values())!=len(entries)
                or report["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]["n"]!=states["SETTLED_LOCAL"]):
            raise ValueError("COHORT_ACCOUNTING")
        out.update(declared_roster_reconciled=True,states={k:states[k] for k in
                   ("PENDING_MATURITY","MATURE_WITHOUT_RESULT","RESULT_CLAIMS_REJECTED","SETTLED_LOCAL")},
                   declared_roster_sha256=_digest(sorted(digests)),evaluation=report,
                   reason="DECLARED_LOCAL_ROSTER_ONLY")
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
        return out
    return out
