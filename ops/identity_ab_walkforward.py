"""Retrospective, leakage-resistant MODEL DIAGNOSTIC on a single raw-source snapshot.

This is NOT a real-time pre-match forecast history. Public source results and
fixture times observed today may have been revised since their historical
dates; "24h before KO" is a simulated cutoff, NOT an archived timestamp.
Do not train, fit, calibrate or select a strategy from these labels.
"""
from datetime import datetime, timedelta, timezone
import math

try:
    from .identity_ab_compare import compare, _instant
    from .identity_ab_openliga_probe import HK
except ImportError:
    from identity_ab_compare import compare, _instant
    from identity_ab_openliga_probe import HK

SCHEMA = "football-king-identity-ab-single-source-retrospective-v1"


def _require(ok, code):
    if not ok:
        raise ValueError(code)


def _loss(vector, y):
    _require(type(vector) is list and len(vector) == 3 and
             all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1
                 for v in vector), "INVALID_RETROSPECTIVE_PROBABILITY")
    return (-math.log(max(vector[y],1e-15)),
            sum((p-int(k==y))**2 for k,p in enumerate(vector)),
            int(max(range(3),key=lambda j:vector[j]) == y),
            int(max(range(3),key=lambda j:vector[j]) == 0))


def assess(rows, *, observed_utc):
    """Score *all* older single-provider FT cases under fixed 24h cutoffs."""
    observed = _instant(observed_utc)
    today_hk = observed.astimezone(HK).date()
    _require(type(rows) is list and len(rows) <= 500,
             "INVALID_WALKFORWARD_INPUT")
    past=[]
    for row in rows:
        _require(type(row) is dict and row.get("status") in
                 ("FINISHED","SCHEDULED"), "INVALID_WALKFORWARD_INPUT")
        if row["status"] == "SCHEDULED":
            _require(row.get("score_ft") is None, "FUTURE_RESULT_LEAKAGE")
            continue
        yscore=row.get("score_ft")
        _require(type(yscore) is list and len(yscore)==2 and
                 all(type(v) is int and 0 <= v <=20 for v in yscore),
                 "INVALID_WALKFORWARD_RESULT")
        ko=_instant(row.get("kickoff_utc"))
        _require(ko.astimezone(HK).date().isoformat()==row.get("date")
                 and ko < observed and
                 ko.astimezone(HK).date()<today_hk,
                 "WALKFORWARD_TIME_OR_RESULT_LEAKAGE")
        past.append(row)
    past.sort(key=lambda row: (row["kickoff_utc"], row["event_id"]))
    _require(len({r["event_id"] for r in past}) == len(past),
             "DUPLICATE_WALKFORWARD_RESULT")
    counters={
        "observed_source_ft":len(past), "legacy_forecasts":0,
        "candidate_forecasts":0,"paired_predictions_scored":0,
        "legacy_only":0,"candidate_only":0,"neither_predicted":0,
        "actual_home_on_paired":0,
        "legacy_home_top_on_paired":0,"candidate_home_top_on_paired":0,
        "legacy_hits_on_paired":0,"candidate_hits_on_paired":0,
        "legacy_log_loss_sum":0.0,"candidate_log_loss_sum":0.0,
        "legacy_brier_sum":0.0,"candidate_brier_sum":0.0,
    }
    for row in past:
        ko=_instant(row["kickoff_utc"])
        as_of=ko-timedelta(hours=24)
        cutoff=as_of.astimezone(HK).date().isoformat()
        # NO outcome label from this fixture, its date, or any later match
        # is present in the rows given to either prediction engine.
        training=[r for r in past if r["date"]<cutoff]
        simulated={**row,"score_ft":None,"status":"SCHEDULED"}
        report=compare(training+[simulated],league="bundesliga",
                       as_of_utc=as_of.isoformat())
        paired=report["paired"]
        counts=report["counts"]
        _require(counts["paired"] in (0,1) and
                 counts["legacy"] in (0,1) and
                 counts["candidate"] in (0,1) and
                 counts["legacy_only"] in (0,1) and
                 counts["candidate_only"] in (0,1),
                 "UNEXPECTED_WALKFORWARD_COVERAGE")
        counters["legacy_forecasts"]+=counts["legacy"]
        counters["candidate_forecasts"]+=counts["candidate"]
        counters["legacy_only"]+=counts["legacy_only"]
        counters["candidate_only"]+=counts["candidate_only"]
        if not paired:
            if not counts["legacy"] and not counts["candidate"]:
                counters["neither_predicted"]+=1
            continue
        _require(paired[0]["event_id"]==row["event_id"] and
                 paired[0]["kickoff_utc"]==ko.isoformat() and
                 paired[0]["comparison_has_result_outcome"] is False,
                 "WALKFORWARD_IDENTITY_MISMATCH")
        y=0 if row["score_ft"][0]>row["score_ft"][1] else (
            1 if row["score_ft"][0]==row["score_ft"][1] else 2)
        score_a=_loss(paired[0]["legacy_1x2"],y)
        score_b=_loss(paired[0]["candidate_1x2"],y)
        counters["paired_predictions_scored"]+=1
        counters["actual_home_on_paired"]+=int(y==0)
        counters["legacy_home_top_on_paired"]+=score_a[3]
        counters["candidate_home_top_on_paired"]+=score_b[3]
        counters["legacy_hits_on_paired"]+=score_a[2]
        counters["candidate_hits_on_paired"]+=score_b[2]
        counters["legacy_log_loss_sum"]+=score_a[0]
        counters["candidate_log_loss_sum"]+=score_b[0]
        counters["legacy_brier_sum"]+=score_a[1]
        counters["candidate_brier_sum"]+=score_b[1]
    n=counters["paired_predictions_scored"]
    summary={
        "paired_cases_scored":n,
        "legacy_top_direction_accuracy_on_paired":(
            round(counters["legacy_hits_on_paired"]/n,6) if n else None),
        "candidate_top_direction_accuracy_on_paired":(
            round(counters["candidate_hits_on_paired"]/n,6) if n else None),
        "legacy_mean_log_loss":(
            round(counters["legacy_log_loss_sum"]/n,6) if n else None),
        "candidate_mean_log_loss":(
            round(counters["candidate_log_loss_sum"]/n,6) if n else None),
        "legacy_mean_brier":(
            round(counters["legacy_brier_sum"]/n,6) if n else None),
        "candidate_mean_brier":(
            round(counters["candidate_brier_sum"]/n,6) if n else None),
    }
    return {
        "schema":SCHEMA,
        "status":"RETROSPECTIVE_SINGLE_SOURCE_UNVERIFIED" if n else "HOLD",
        "as_of_analysis_utc":observed.isoformat(),
        "hypothetical_prediction_cutoff_hours_before_ko":24,
        "historical_source_available_at_cutoff_authenticated":False,
        "source_results_independently_verified":False,
        "historical_kickoff_time_authenticated":False,
        "real_pre_match_prediction_archive_exists":False,
        "retrospective_diagnostic_only_not_prospective_performance":True,
        "no_outcome_leakage_in_model_inputs_by_construction":True,
        "independent_certified_settlement_count":0,
        "counts":counters,
        "summary":summary,
        "accuracy_uplift_proven":False,
        "positive_ev_verified":False,
        "production_recommendations":"DISABLED",
    }
