"""Fixed retrospective model triage, NEVER a production selector.

Only the existing 186-match reused score audit is in scope. All report
fields are untrusted until separately replayed; validation below checks
internal consistency, not authentic source evidence or prospective skill.
No changes to model weights or inference, no promotion, no odds or EV.
"""
import math
from ops.dynamic_2026_date_split_audit import SCHEMA, MODELS, CLASSES

PIN = "09aac809e317f3004c69720a38addb656c49ebb19f1937deab96f96e3362257a"
N = 186
MIN_CLUSTERS = 30  # conservative research triage choice, not fitted


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _hold(reason):
    return {"status": "HOLD", "reason": reason, "production_recommendations": "DISABLED",
            "model_promoted": False, "certified_prospective_samples": 0,
            "positive_ev_verified": False, "production_weights_changed": False,
            "prospective_skill_verified": False, "research_triage": {}}


def evaluate(report):
    try:
        if type(report) is not dict or report.get("schema") != SCHEMA:
            raise ValueError()
        if (report.get("status") != "HOLD"
                or report.get("production_recommendations") != "DISABLED"
                or report.get("source_sha256") != PIN
                or report.get("tested_models") != list(MODELS)
                or report.get("reason") != "EXPLORATORY_REUSED_2026_RESULTS_NOT_CERTIFIED_FORWARD_TEST"
                or any(report.get(k) is not False for k in (
                    "positive_ev_verified", "model_promoted",
                    "original_holdout_untouched_confirmatory",
                    "independently_timestamped_prematch_vectors",
                    "test_scores_passed_to_model_fit", "real_quote_prices_verified"))
                or any(type(report.get(k)) is not int or report[k] != v for k,v in (
                    ("training_real_matches",260), ("source_test_rows",N),
                    ("same_eligible_heldout_games",N), ("certified_prospective_samples",0),
                    ("bootstrap_draws",2000)))):
            raise ValueError()
        scores = report["per_model_scores"]
        if set(scores) != set(MODELS):
            raise ValueError()
        for model in MODELS:
            if set(scores[model]) != set(CLASSES):
                raise ValueError()
            for market, classes in CLASSES.items():
                item = scores[model][market]
                if (type(item["n"]) is not int or item["n"] != N
                        or not _number(item["mean_brier"],0,2)
                        or not _number(item["mean_logloss"],0,100)):
                    raise ValueError()
                counts = item["observed_class_counts"]
                probs = item["mean_forecast_class_probability"]
                if (set(counts) != set(classes) or set(probs) != set(classes)
                        or any(type(v) is not int or v < 0 for v in counts.values())
                        or sum(counts.values()) != N
                        or counts != scores["dixon_coles"][market]["observed_class_counts"]
                        or any(not _number(v,0,1) for v in probs.values())
                        or abs(math.fsum(probs.values())-1)>1e-5):
                    raise ValueError()
        paired = report["dynamic_minus_dixon_coles_paired_date_cluster_CI95"]
        if set(paired) != set(CLASSES):
            raise ValueError()
        triage = {}
        for market in CLASSES:
            if set(paired[market]) != {"brier","logloss"}:
                raise ValueError()
            clearly_worse = []
            for metric in ("brier","logloss"):
                item = paired[market][metric]
                delta = (scores["dynamic_score_poisson"][market]["mean_"+metric]
                         - scores["dixon_coles"][market]["mean_"+metric])
                if (not _number(item["mean_delta"],-100,100)
                        or abs(item["mean_delta"]-delta)>2e-6
                        or type(item["distinct_date_clusters"]) is not int
                        or not 5 <= item["distinct_date_clusters"] <= N):
                    raise ValueError()
                ci = item["interval_95pct"]
                if (type(ci) is not list or len(ci)!=2
                        or any(not _number(v,-100,100) for v in ci)
                        or ci[0]>ci[1] or type(item["includes_zero"]) is not bool):
                    raise ValueError()
                # Rounding can move a near-zero endpoint across zero. Never
                # treat that as clear inferiority; reject material contradiction.
                if ci[0]>1e-6 or ci[1]<-1e-6:
                    if item["includes_zero"]:
                        raise ValueError()
                elif ci[0]<-1e-6 and ci[1]>1e-6 and not item["includes_zero"]:
                    raise ValueError()
                clearly_worse.append(item["distinct_date_clusters"]>=MIN_CLUSTERS
                                     and delta>0 and ci[0]>1e-6)
            triage[market] = ("DEPRIORITIZE_ON_REUSED_COHORT" if all(clearly_worse)
                              else "INCONCLUSIVE_KEEP_RESEARCH_ONLY")
        return {**_hold("EXPLORATORY_TRIAGE_NOT_PRODUCTION_SELECTION"),
                "research_triage": triage,
                "cohort_size":N, "reference_model":"dixon_coles",
                "candidate_model":"dynamic_score_poisson",
                "independent_confirmatory_cohort_required":True}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return _hold("INVALID_OR_INCOMPLETE_REUSED_AUDIT")
