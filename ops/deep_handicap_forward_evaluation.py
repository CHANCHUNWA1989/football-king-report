"""Paired deep-spread forecast evaluation, offline research only.

Validates the *structure* of supplied claims; never authenticates sources,
timestamps, actual market lines, or out-of-sample provenance. No odds, profit,
betting decisions or production integration.
"""
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from asian_handicap_research import TYPES, grade, quarter_units
from deep_handicap_grade_calibration import diagnose

SCHEMA = "football-king-deep-handicap-paired-evaluation-v1"
MAX_ROWS = 10000
EPS = 1e-15


def _time(s):
    if not isinstance(s, str):
        raise ValueError("BAD_TIME")
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)


def _id(v):
    if not isinstance(v, str) or not v or len(v) > 160 or v != v.strip():
        raise ValueError("BAD_IDENTITY")
    return v


def _dist(p):
    if not isinstance(p, dict) or set(p) != set(TYPES):
        raise ValueError("BAD_GRADE_KEYS")
    if any(type(v) not in (int, float) or not math.isfinite(v) or
           not 0 <= v <= 1 for v in p.values()):
        raise ValueError("BAD_PROBABILITY")
    total = math.fsum(p.values())
    if abs(total - 1) > 1e-6:
        raise ValueError("BAD_PROBABILITY_MASS")
    return {k: p[k]/total for k in TYPES}


def _identity(row):
    return (_id(row["league_id"]), _id(row["fixture_id"]))


def _parse(row, as_of):
    key = _identity(row)
    kind = row["data_kind"]
    if kind not in ("SYNTHETIC", "EXTERNAL_UNAUTHENTICATED"):
        raise ValueError("UNKNOWN_DATA_KIND")
    home, away = _id(row["home_id"]), _id(row["away_id"])
    if home == away:
        raise ValueError("SAME_TEAM")
    ko, cutoff = _time(row["kickoff_utc"]), _time(row["information_cutoff_utc"])
    if cutoff > ko - timedelta(minutes=10):
        raise ValueError("CUTOFF_TOO_LATE")
    units = quarter_units(row["handicap"])
    side = row["side"]
    if units > -6 or side not in ("HOME", "AWAY"):
        raise ValueError("NOT_DEEP_FAVOURITE_LINE")
    predictions = []
    model_ids = set()
    for name in ("baseline", "challenger"):
        p = row[name]
        if (_identity(p) != key or _id(p["home_id"]) != home or
                _id(p["away_id"]) != away or _time(p["kickoff_utc"]) != ko or
                p["side"] != side or quarter_units(p["handicap"]) != units):
            raise ValueError("PREDICTION_IDENTITY_MISMATCH")
        if _time(p["information_cutoff_utc"]) != cutoff:
            raise ValueError("UNEQUAL_INFORMATION_CUTOFF")
        if not cutoff <= _time(p["recorded_utc"]) <= ko - timedelta(minutes=10):
            raise ValueError("PREDICTION_NOT_PREMATCH")
        model_ids.add(_id(p["model_id"]))
        _id(p["archive_reference"])
        dist = _dist(p["probabilities"])
        # Reject mass on logically impossible outcomes for this line.
        feasible = {grade(max(0, m), max(0, -m), "HOME", units/4)
                    for m in range(-25, 26)}
        if any(dist[k] > 1e-8 for k in TYPES if k not in feasible):
            raise ValueError("IMPOSSIBLE_GRADE_MASS")
        predictions.append(dist)
    if len(model_ids) != 2:
        raise ValueError("DUPLICATE_MODEL")
    observations = row["results"]
    if not isinstance(observations, list) or not 2 <= len(observations) <= 10:
        raise ValueError("MISSING_RESULT_CLAIMS")
    scores = set()
    providers = set()
    for obs in observations:
        if (_identity(obs) != key or _id(obs["home_id"]) != home or
                _id(obs["away_id"]) != away or _time(obs["kickoff_utc"]) != ko):
            raise ValueError("RESULT_IDENTITY_MISMATCH")
        if obs["status"] != "FINISHED_90_MINUTES":
            raise ValueError("NOT_REGULATION_FINAL")
        if not ko + timedelta(minutes=105) <= _time(obs["captured_utc"]) <= as_of:
            raise ValueError("RESULT_TIME_INVALID")
        provider = _id(obs["provider_id"])
        _id(obs["evidence_reference"])
        if provider in providers:
            raise ValueError("DUPLICATE_RESULT_PROVIDER")
        providers.add(provider)
        score = obs["score_ft"]
        if (not isinstance(score, (list, tuple)) or len(score) != 2 or
                any(type(x) is not int or not 0 <= x <= 25 for x in score)):
            raise ValueError("BAD_SCORE")
        scores.add(tuple(score))
    if len(scores) != 1:
        raise ValueError("CONFLICTING_RESULT_CLAIMS")
    h, a = scores.pop()
    actual = grade(h, a, side, units/4)
    return kind, key[0], units, actual, predictions


def _summary(rows):
    n = len(rows)
    out = {"n": n, "grades": dict.fromkeys(TYPES, 0),
           "baseline": None, "challenger": None, "paired_delta": None}
    if not n:
        return out
    for _, _, _, y, _ in rows:
        out["grades"][y] += 1
    for idx, name in enumerate(("baseline", "challenger")):
        brier, logloss, full = [], [], []
        for _, _, _, y, preds in rows:
            p = preds[idx]
            brier.append(math.fsum((p[k] - (k == y))**2 for k in TYPES))
            logloss.append(-math.log(max(EPS, p[y])))
            full.append(p["FULL_WIN"])
        out[name] = {"multiclass_brier": math.fsum(brier)/n,
                     "log_loss": math.fsum(logloss)/n,
                     "mean_full_win_probability": math.fsum(full)/n,
                     "observed_full_win_fraction": out["grades"]["FULL_WIN"]/n}
    out["paired_delta"] = {k: out["challenger"][k]-out["baseline"][k]
                           for k in ("multiclass_brier", "log_loss")}
    return out


def _paired_uncertainty(records):
    """Resample entire UTC ISO weeks, preserving within-week pair dependence.

    Percentile intervals are descriptive, not authenticated confidence bounds.
    Inter-week independence/stationarity is not established. No multiplicity
    adjustment; subgroup results are descriptive only.
    """
    n = len(records)
    weeks = defaultdict(list)
    model_pairs = set()
    for row, week, pair in records:
        _, _, _, y, predictions = row
        p, q = predictions
        db = math.fsum((q[k] - (k == y))**2 -
                       (p[k] - (k == y))**2 for k in TYPES)
        dl = math.log(max(EPS, p[y])) - math.log(max(EPS, q[y]))
        weeks[week].append((db, dl))
        model_pairs.add(pair)
    out = {"n": n, "utc_iso_week_count": len(weeks),
           "method": "PAIRED_WEEK_CLUSTER_PERCENTILE_BOOTSTRAP",
           "descriptive_only": True, "source_authenticated": False,
           "verified_improvement": False, "intervals": None,
           "bootstrap_replicates": 0}
    if len(model_pairs) > 1:
        out["status"] = "MIXED_MODEL_VERSIONS"
        return out
    if n < 300 or len(weeks) < 12:
        out["status"] = "INSUFFICIENT_SAMPLE"
        return out
    if len(weeks) > 520:
        out["status"] = "WEEK_LIMIT_EXCEEDED"
        return out
    blocks = [(len(weeks[w]), math.fsum(x[0] for x in weeks[w]),
               math.fsum(x[1] for x in weeks[w])) for w in sorted(weeks)]
    # Fixed seed for reproducibility; resample clusters, not individual fixtures.
    rng = random.Random(20261127)
    brier, logs = [], []
    for _ in range(2000):
        count, sb, sl = 0, 0.0, 0.0
        for _ in blocks:
            k, b, l = blocks[rng.randrange(len(blocks))]
            count += k
            sb += b
            sl += l
        brier.append(sb/count)
        logs.append(sl/count)

    def percentile_interval(values):
        values.sort()
        def at(q):
            index = q*(len(values)-1)
            i = int(index)
            return values[i]+(index-i)*(values[min(i+1,len(values)-1)]-values[i])
        return {"lower": at(.025), "upper": at(.975)}

    out.update(status="DESCRIPTIVE_INTERVAL_ONLY", bootstrap_replicates=2000,
               intervals={"multiclass_brier_delta": percentile_interval(brier),
                          "log_loss_delta": percentile_interval(logs)},
               point_estimate={"multiclass_brier_delta": math.fsum(x[1] for x in blocks)/n,
                               "log_loss_delta": math.fsum(x[2] for x in blocks)/n},
               nominal_percentile_level=.95)
    return out


def _full_win_calibration(records):
    """Fixed-width reliability bins; empty bins remain null, not zero error."""
    result = {}
    for i, name in enumerate(("baseline", "challenger")):
        bins = [[] for _ in range(10)]
        for row, _, _ in records:
            _, _, _, y, preds = row
            p = preds[i]["FULL_WIN"]
            bins[min(9, int(p*10))].append((p, y == "FULL_WIN"))
        report = []
        for b, values in enumerate(bins):
            n = len(values)
            report.append({"lower": b/10, "upper": (b+1)/10,
                           "upper_inclusive": b == 9, "n": n,
                           "mean_forecast": math.fsum(v[0] for v in values)/n if n else None,
                           "observed_fraction": math.fsum(v[1] for v in values)/n if n else None})
        result[name] = report
    return {"descriptive_only": True, "bins": result}


def evaluate(rows, *, as_of_utc):
    """One fixture per cohort; reject *all* duplicates, never select winners."""
    as_of = _time(as_of_utc)
    report = {"schema": SCHEMA, "status": "HOLD",
              "production_recommendations": "DISABLED",
              "research_only": True, "qualifies_for_betting": False,
              "positive_expected_value_verified": False,
              "source_authentication_performed": False,
              "true_forward_sample_count": 0,
              "accuracy_improvement_verified": False,
              "confidence_interval_available": False,
              "reason": "STRUCTURAL_EVALUATION_ONLY",
              "rejected": {}, "cohorts": {}}
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        report["reason"] = "INVALID_INPUT_BATCH"
        return report
    rejects = Counter()
    keys = Counter()
    keyed = []
    for r in rows:
        try:
            k = _identity(r)
            keys[k] += 1
            keyed.append((k, r))
        except (ValueError, TypeError, KeyError):
            rejects["BAD_IDENTITY"] += 1
    accepted = defaultdict(list)
    paired_records = defaultdict(list)
    for k, r in keyed:
        if keys[k] != 1:
            rejects["DUPLICATE_FIXTURE"] += 1
            continue
        try:
            v = _parse(r, as_of)
            ko = _time(r["kickoff_utc"]).isocalendar()
            pair = (r["baseline"]["model_id"], r["challenger"]["model_id"])
            accepted[v[0]].append(v)
            paired_records[v[0]].append((v, (ko.year, ko.week), pair))
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            reason = str(exc)
            # Do not echo unknown input values or raw evidence.
            if not reason.isupper() or len(reason) > 80:
                reason = "INVALID_RECORD"
            rejects[reason] += 1
    for kind in ("SYNTHETIC", "EXTERNAL_UNAUTHENTICATED"):
        cohort = accepted[kind]
        groups = defaultdict(list)
        for v in cohort:
            groups[(v[1], v[2])].append(v)
        report["cohorts"][kind] = {"overall": _summary(cohort),
            "paired_uncertainty": _paired_uncertainty(paired_records[kind]),
            "full_win_calibration": _full_win_calibration(paired_records[kind]),
            "stratified_grade_calibration": diagnose(paired_records[kind]),
            "by_league_and_line": [
                {"league_id": league, "handicap": units/4, **_summary(values)}
                for (league, units), values in sorted(groups.items())]}
    report["rejected"] = dict(rejects)
    return report
