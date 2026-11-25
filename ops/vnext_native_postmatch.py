"""Research-only post-match scoring of a frozen native replay, never live EV."""
import math
from datetime import timedelta
from inplay_state_challenger_vnext import _clock, _valid_id, remaining_matrix
from live_snapshot_adapter import hold
from score_distribution_vnext import grade_score, GRADE_NAMES, one_x_two, market_distribution
from vnext_native_series_replay import replay_series, MAX_CUTS

# Prespecified, non-overlapping regulation-time bands. Earliest cut only.
BANDS = ((0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90))
CLASSES = ("HOME", "DRAW", "AWAY")

def _brier(p, outcome, labels):
    return math.fsum((p[k]-int(k==outcome))**2 for k in labels)

def _logloss(p, outcome):
    return -math.log(max(1e-15, p[outcome]))

RESULT_KEYS = {"fixture_id","origin","kickoff_utc","completed_utc",
               "observed_utc","received_utc","scope","status","home","away"}

def postmatch(raw, archive_sha256, *, fixture_id, home_native_id,
              away_native_id, kickoff_utc, cuts, results, as_of_utc):
    """Two claimed final-result records, not independent authentication.
    Replays every cut; never picks a favorable cut or grants sample credit.
    """
    try:
        kickoff, as_of = _clock(kickoff_utc), _clock(as_of_utc)
        if type(cuts) is not list or not 1 <= len(cuts) <= MAX_CUTS:
            return hold("INVALID_POSTMATCH")
        for cut in cuts:
            if _clock(cut["envelope"]["model"]["kickoff_utc"]) != kickoff:
                return hold("SERIES_KICKOFF_MISMATCH")
        series = replay_series(raw,archive_sha256,fixture_id=fixture_id,
            home_native_id=home_native_id,away_native_id=away_native_id,
            kickoff_utc=kickoff_utc,cuts=cuts)
        if series.get("series_status") != "STRUCTURAL_RESEARCH_ONLY":
            return hold("POSTMATCH_SERIES_REJECTED")
        last=series["cuts"][-1]
        if type(results) is not list or len(results)!=2:
            return hold("INVALID_FINAL_RESULTS")
        for r in results:
            if (type(r) is not dict or set(r)!=RESULT_KEYS
                    or r["fixture_id"]!=fixture_id or not _valid_id(r["origin"])
                    or r["scope"]!="FULL_MATCH_REGULATION" or r["status"]!="FINISHED"
                    or _clock(r["kickoff_utc"])!=kickoff
                    or any(type(r[k]) is not int or not 0<=r[k]<=20 for k in ("home","away"))):
                return hold("INVALID_FINAL_RESULTS")
            completed, observed, received=(_clock(r[k]) for k in
                ("completed_utc","observed_utc","received_utc"))
            if (completed<kickoff+timedelta(minutes=90)
                    or completed.timestamp()<=last["decision_epoch"]
                    or not completed<=observed<=received<=as_of):
                return hold("FINAL_RESULT_CLOCK_ORDER")
        a,b=results
        if (a["origin"].casefold()==b["origin"].casefold()
                or (a["home"],a["away"])!=(b["home"],b["away"])):
            return hold("FINAL_RESULT_CONFLICT")
        h,v=a["home"],a["away"]
        if h<last["score"][0] or v<last["score"][1]:
            return hold("FINAL_SCORE_CORRECTION_REVIEW")
        outcome="HOME" if h>v else "AWAY" if h<v else "DRAW"
        scored=[]
        # Both models share the frozen rates, elapsed time and current score.
        # Baseline does not modify remaining scoring intensity for score gap or cards.
        for cut, source in zip(series["cuts"], cuts):
            d=cut["research_diagnostics"]
            p=d["probabilities_1x2"]
            market,=d["diagnostic_distributions"]
            grade=grade_score(h,v,market=market["market"],side=market["side"],line=market["line"])
            mp=market["outcome_probabilities"]
            pre=source["envelope"]["model"]["prematch"]
            fraction=(90-cut["minute"])/90.0
            grid=remaining_matrix(pre["expected_home_goals"]*fraction,
                pre["expected_away_goals"]*fraction,*cut["score"])
            bp=one_x_two(grid)
            bm=market_distribution(grid,market=market["market"],side=market["side"],
                line=market["line"])["outcome_probabilities"]
            baseline_1x2=_brier(bp,outcome,CLASSES)
            challenger_1x2=_brier(p,outcome,CLASSES)
            baseline_market=_brier(bm,grade,GRADE_NAMES)
            challenger_market=_brier(mp,grade,GRADE_NAMES)
            scored.append({"decision_epoch":cut["decision_epoch"],"minute":cut["minute"],
                "cut_sha256_unattested":cut["cut_sha256_unattested"],
                "probabilities_1x2":p,"actual_1x2":outcome,
                "brier_1x2":challenger_1x2,
                "red_cards":cut["red_cards"],"score":cut["score"],
                "market":market["market"],"side":market["side"],"line":market["line"],
                "settlement_grade":grade,"grade_probabilities":mp,
                "brier_market":challenger_market,
                "paired_baseline":{"probabilities_1x2":bp,"grade_probabilities":bm,
                    "brier_1x2":baseline_1x2,"brier_market":baseline_market,
                    "log_loss_1x2":_logloss(bp,outcome)},
                "paired_delta_baseline_minus_challenger":{
                    "brier_1x2":baseline_1x2-challenger_1x2,
                    "brier_market":baseline_market-challenger_market,
                    "log_loss_1x2":_logloss(bp,outcome)-_logloss(p,outcome)}})
        selected=[]
        for start,end in BANDS:
            first=next((row for row in scored if start<=row["minute"]<end),None)
            if first is not None:
                selected.append({"minute_band":[start,end],
                    "decision_epoch":first["decision_epoch"],
                    "cut_sha256_unattested":first["cut_sha256_unattested"],
                    "paired_delta_baseline_minus_challenger":first["paired_delta_baseline_minus_challenger"]})

        return {**hold("UNAUTHENTICATED_POSTMATCH_RESEARCH"),
                "postmatch_status":"STRUCTURAL_RESEARCH_ONLY","fixture_id":fixture_id,
                "final_score_claimed":[h,v],"cut_count":len(scored),
                "fixture_count":1,"cuts":scored,"verified_forward_sample_credit":0,
                "paired_baseline_id":"fixed-prematch-rates-clock-and-current-score-v1",
                "band_selection":"earliest-cut-per-fixed-15-minute-band",
                "band_diagnostics":selected,"pooled_accuracy":None,
                "weight_updates_applied":False,"statistical_promotion_gate":False,
                "final_result_authenticated":False,"actual_quote_verified":False,
                "model_edge":None,"realized_roi":None}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_POSTMATCH")
