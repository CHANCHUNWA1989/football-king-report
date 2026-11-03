"""KPL V17: strictly chronological Elo *benchmark* and complete-BO shadow replay.

Never retrieves third-party match data, trains on future labels, tunes Elo K on
the test set, or issues picks. All records are caller-supplied; timestamp,
rights, and source-grade claims are NOT independently authenticated.
Always returns HOLD/DISABLED even when synthetic metrics look good.
"""
from __future__ import annotations

import heapq
import math
import random
from collections import defaultdict
from datetime import datetime
from research.kpl_v11_forecast_archive import _time

ROW_KEYS = frozenset({
    "series_id", "game_number", "team_a", "team_b", "winner_team_id",
    "patch_id", "forecast_at", "game_start_at", "result_observed_at",
    "source_id", "source_class", "source_record_sha256"})
SOURCE_CLASSES = frozenset({"SYNTHETIC", "UNVERIFIED_PUBLIC", "LICENSED_OFFLINE_CLAIM"})
SHA_CHARS = frozenset("0123456789abcdef")


def _ident(value):
    return (isinstance(value, str) and bool(value)
            and value.strip() == value and len(value) <= 128)


def _p(r_a, r_b, scale):
    return 1 / (1 + 10 ** ((r_b - r_a) / scale))


def _score(probs, labels):
    if len(probs) != len(labels) or not probs:
        raise ValueError("empty/mismatched score sample")
    n = len(probs)
    brier = sum((p - y) ** 2 for p, y in zip(probs, labels)) / n
    logloss = -sum(y * math.log(max(p, 1e-15)) +
                   (1-y) * math.log(max(1-p, 1e-15))
                   for p, y in zip(probs, labels)) / n
    directions = [(p > .5) == bool(y) for p, y in zip(probs, labels) if p != .5]
    ece = 0.
    for bucket in range(5):
        samples = [(p,y) for p,y in zip(probs, labels)
                   if min(4, int(p * 5)) == bucket]
        if samples:
            ece += len(samples) / n * abs(
                sum(p for p,_ in samples)/len(samples) -
                sum(y for _,y in samples)/len(samples))
    return {"count":n,"brier":brier,"log_loss":logloss,"ece_5_bins":ece,
            "direction_count":len(directions),
            "direction_coverage":len(directions)/n,
            "direction_accuracy":(sum(directions)/len(directions) if directions else None)}


def _validate_rows(rows):
    if not isinstance(rows, list) or not rows or len(rows) > 100000:
        raise ValueError("invalid history length")
    series = defaultdict(list)
    sources = set()
    seen = set()
    digests = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            raise ValueError("invalid history schema")
        if (not all(_ident(row[k]) for k in
                    ("series_id","team_a","team_b","patch_id","source_id"))
            or row["team_a"] == row["team_b"]
            or row["winner_team_id"] not in (row["team_a"],row["team_b"])
            or type(row["game_number"]) is not int or not 1 <= row["game_number"] <= 7):
            raise ValueError("invalid series identity or result")
        digest = row["source_record_sha256"]
        if (not isinstance(digest,str) or len(digest) != 64
            or any(ch not in SHA_CHARS for ch in digest)):
            raise ValueError("invalid source digest")
        if not isinstance(row["source_class"], str) or row["source_class"] not in SOURCE_CLASSES:
            raise ValueError("invalid source class")
        if digest in digests:
            raise ValueError("duplicate source digest across maps")
        digests.add(digest)
        sources.add(row["source_class"])
        t0, t1, t2 = (_time(row[k]) for k in
                      ("forecast_at","game_start_at","result_observed_at"))
        if not t0 < t1 < t2:
            raise ValueError("forecast or outcome time leakage")
        slot=(row["series_id"],row["game_number"])
        if slot in seen:
            raise ValueError("duplicate series game")
        seen.add(slot)
        series[row["series_id"]].append((row,t0,t1,t2))
    if len(sources) != 1:
        raise ValueError("cannot mix synthetic and unverified/licensed data grades")
    series_meta = []
    for sid, games in series.items():
        games.sort(key=lambda v:v[0]["game_number"])
        if [v[0]["game_number"] for v in games] != list(range(1,len(games)+1)):
            raise ValueError("missing/interleaved series maps")
        if not 4 <= len(games) <= 7:
            raise ValueError("incomplete or oversized BO7 series")
        teams = (games[0][0]["team_a"], games[0][0]["team_b"])
        patch = games[0][0]["patch_id"]
        score = {team:0 for team in teams}
        previous_start = None
        for index,(row, forecast, started, observed) in enumerate(games):
            if (row["team_a"],row["team_b"]) != teams or row["patch_id"] != patch:
                raise ValueError("team orientation or patch changes inside a series")
            if previous_start is not None and forecast <= previous_start:
                raise ValueError("series game chronology invalid")
            if max(score.values()) >= 4:
                raise ValueError("games after series already decided")
            score[row["winner_team_id"]]+=1
            previous_start = started
        if max(score.values()) != 4:
            raise ValueError("series has no fourth winning map")
        series_meta.append((games[0][1], sid, games[-1][3], games))
    series_meta.sort()
    return series_meta, sources.pop()


def replay_elo_shadow(rows, *, model_frozen_at, registered_series_ids,
                      universe_registered_at, elo_k=16.0, elo_scale=400.0,
                      train_fraction=0.7, min_test_series=20, min_test_maps=70,
                      repetitions=600, seed=17):
    """Prequential forecast before EACH outcome is observed; no future labels.

    Elo is a deliberately simple, uncalibrated 50/50-benchmark challenger,
    never an already verified winner-probability model. Hyperparameters and
    split must be selected *before* looking at this evaluation's outcomes.
    """
    if (type(elo_k) not in (int,float) or not math.isfinite(elo_k) or not 0 <= elo_k <= 64
        or type(elo_scale) not in (int,float) or not math.isfinite(elo_scale)
        or not 50 <= elo_scale <= 2000
        or type(train_fraction) not in (int,float) or not 0 < train_fraction < 1
        or type(min_test_series) is not int or min_test_series < 1
        or type(min_test_maps) is not int or min_test_maps < 1
        or type(repetitions) is not int or not 200 <= repetitions <= 3000):
        raise ValueError("invalid frozen benchmark policy")
    series, source_class = _validate_rows(rows)
    frozen = _time(model_frozen_at)
    first_forecast = min(x[0] for x in series)
    if len(series) < 2 or frozen > first_forecast:
        raise ValueError("model policy frozen after historical test began")
    if (not isinstance(registered_series_ids, list)
            or not 2 <= len(registered_series_ids) <= 100000
            or any(not _ident(sid) for sid in registered_series_ids)
            or len(set(registered_series_ids)) != len(registered_series_ids)):
        raise ValueError("invalid registered series universe")
    if _time(universe_registered_at) > first_forecast:
        raise ValueError("series universe registered after first forecast")
    if registered_series_ids != [item[1] for item in series]:
        raise ValueError("registered series universe coverage/order mismatch")
    cutoff = max(1,min(len(series)-1,int(len(series)*train_fraction)))
    first_test_at = series[cutoff][0]
    if any(s[2] >= first_test_at for s in series[:cutoff]):
        raise ValueError("test split overlaps unobserved training outcome")
    all_games = [game[0] for _,_,_,group in series for game in group]
    all_games.sort(key=lambda row:(_time(row["forecast_at"]),row["series_id"],
                                   row["game_number"]))
    ratings = defaultdict(lambda:1500.0)
    pending = []
    predictions = []
    for row in all_games:
        at = _time(row["forecast_at"])
        while pending and pending[0][0] < at:
            _,_,historical = heapq.heappop(pending)
            a = (historical["patch_id"],historical["team_a"])
            b = (historical["patch_id"],historical["team_b"])
            pa = _p(ratings[a],ratings[b],elo_scale)
            winner_a = int(historical["winner_team_id"] == historical["team_a"])
            delta = elo_k * (winner_a - pa)
            ratings[a] += delta
            ratings[b] -= delta
        a,b=(row["patch_id"],row["team_a"]),(row["patch_id"],row["team_b"])
        p = _p(ratings[a],ratings[b],elo_scale)
        predictions.append({
            "series_id":row["series_id"],"game_number":row["game_number"],
            "team_a":row["team_a"],"team_b":row["team_b"],
            "probability_a":p,
            "forecast_at":row["forecast_at"],"result_observed_at":row["result_observed_at"],
            "outcome_a":int(row["winner_team_id"] == row["team_a"]),
            "phase":"PRE_MAP_RESULTS_ONLY", "is_calibrated_probability":False,
            "research_only":True})
        heapq.heappush(pending,(_time(row["result_observed_at"]),
                                len(predictions),row))
    train_set = {s[1] for s in series[:cutoff]}
    test_set = {s[1] for s in series[cutoff:]}
    test = [x for x in predictions if x["series_id"] in test_set]
    if len(test_set) < min_test_series or len(test) < min_test_maps:
        return {"status":"HOLD","reasons":["INSUFFICIENT_INDEPENDENT_HOLDOUT_SERIES_OR_MAPS"],
                "train_series":len(train_set),"test_series":len(test_set),
                "test_maps":len(test),"source_class":source_class,
                "real_kpl_accuracy_verified":False,
                "production_recommendations":"DISABLED","live_execution_allowed":False,
                "research_only":True}
    ps=[r["probability_a"] for r in test]
    ys=[r["outcome_a"] for r in test]
    model=_score(ps,ys)
    fair=_score([0.5]*len(test),ys)
    per_series=[]
    for sid in test_set:
        subset=[r for r in test if r["series_id"] == sid]
        delta=sum(0.25-(r["probability_a"]-r["outcome_a"])**2 for r in subset)
        per_series.append((len(subset),delta))
    rng=random.Random(seed)
    gains=[]
    for _ in range(repetitions):
        draw=[per_series[rng.randrange(len(per_series))]
              for __ in range(len(per_series))]
        gains.append(sum(s for _,s in draw)/sum(n for n,_ in draw))
    gains.sort()
    lower=gains[int(0.05*repetitions)]
    improvement=fair["brier"]-model["brier"]
    reasons=[]
    if improvement <= 0 or lower <= 0:
        reasons.append("NO_SERIES_CLUSTERED_BRIER_GAIN")
    if model["ece_5_bins"] > 0.08:
        reasons.append("CALIBRATION_ERROR_TOO_HIGH_FOR_RESEARCH")
    reasons.extend(["HISTORIC_SOURCE_AUTHENTICITY_AND_RIGHTS_NOT_INDEPENDENTLY_VERIFIED",
                    "BENCHMARK_ELO_NOT_REAL_KPL_CALIBRATION"])
    return {
        "status":"HOLD","source_class":source_class,
        "train_series":len(train_set),"test_series":len(test_set),
        "test_maps":len(test),"train_map_count":len(predictions)-len(test),
        "series_universe_registered_count":len(registered_series_ids),
        "series_universe_registration_independently_authenticated":False,
        "elo_model":model,"uniform_50_baseline":fair,
        "paired_brier_gain_vs_uniform_50":improvement,
        "series_cluster_bootstrap_gain_lower_one_sided_95":lower,
        "paired_comparison_better_by_predeclared_gate":
            bool(improvement > 0 and lower > 0 and model["ece_5_bins"] <= 0.08),
        "reasons":reasons,
        "test_forecasts":test,
        "real_kpl_accuracy_verified":False,
        "provider_data_rights_independently_verified":False,
        "source_authenticity_independently_verified":False,
        "model_calibrated_on_real_kpl":False,
        "positive_ev_verified":False,
        "production_recommendations":"DISABLED",
        "live_execution_allowed":False,"research_only":True}
