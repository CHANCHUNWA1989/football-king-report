"""Red-card evidence intake and exploratory xG / prospective cohort scaffold.

Input bytes must come from an authorized collector. Matching observations,
local hashes and declared timestamps do NOT authenticate publishers or prove
prospective capture. This module never awards verified sample credit.
"""
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

FLAGS = dict(status="HOLD", production_recommendations="DISABLED",
             independently_verified=False, promotion_allowed=False)
MAX_BYTES = 256_000


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def stamp(value):
    require(isinstance(value, str), "BAD_TIMESTAMP")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(t.utcoffset() is not None, "NAIVE_TIMESTAMP")
    return t


def ident(s):
    require(isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", s),
            "BAD_IDENTIFIER")
    return s


def number(x, lo, hi):
    require(type(x) in (int, float) and math.isfinite(x) and lo <= x <= hi,
            "BAD_NUMBER")
    return float(x)


def score(x):
    require(isinstance(x, list) and len(x) == 2 and
            all(type(v) is int and 0 <= v <= 25 for v in x), "BAD_SCORE")
    return tuple(x)


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "BAD_CAPTURE_BYTES")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    require(isinstance(result, dict), "BAD_CAPTURE_OBJECT")
    return result


def event(raw):
    d = decode(raw)
    for key in ("fixture_id", "player_id", "publisher_id", "origin_group"):
        ident(d[key])
    require(d["role"] in ("OFFICIAL", "INDEPENDENT"), "BAD_ROLE")
    require(d["event_type"] == "RED_CARD" and d["side"] in ("HOME", "AWAY"),
            "BAD_EVENT")
    # First single dismissal only; extra time and second dismissals require
    # separate protocols. Collector must normalize clock to regulation seconds.
    require(type(d["clock_s"]) is int and 0 <= d["clock_s"] < 5400, "BAD_CLOCK")
    require(d["prior_reds"] == [0, 0] and
            all(type(v) is int for v in d["prior_reds"]), "MULTIPLE_CARDS_UNSUPPORTED")
    score(d["score"])
    require(stamp(d["kickoff_utc"]) <= stamp(d["event_utc"]) <=
            stamp(d["captured_utc"]), "BAD_EVENT_CHRONOLOGY")
    return d


def agree(official, other):
    a, b = event(official), event(other)
    require(a["role"] == "OFFICIAL" and b["role"] == "INDEPENDENT", "BAD_ROLES")
    require(a["publisher_id"].casefold() != b["publisher_id"].casefold() and
            a["origin_group"].casefold() != b["origin_group"].casefold(), "SHARED_ORIGIN")
    for key in ("fixture_id", "player_id", "event_type", "side", "clock_s",
                "score", "prior_reds"):
        require(a[key] == b[key], "EVENT_CONFLICT_" + key.upper())
    for key in ("kickoff_utc", "event_utc"):
        require(stamp(a[key]) == stamp(b[key]), "EVENT_TIME_CONFLICT")
    return a, b


def archive_candidate(root, official, other):
    """Content-addressed normalized input bytes; local integrity, not attestation."""
    a, b = agree(official, other)
    manifest = dict(FLAGS, schema="red-card-event-candidate-v1",
                    agreement="AGREED_UNVERIFIED", fixture_id=a["fixture_id"],
                    official_sha256=sha(official), independent_sha256=sha(other),
                    external_witness_verified=False, eligible_for_model_scoring=False)
    raw_manifest = canonical(manifest)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Exclusive directory creation: no overwrite or silent replacement.
    dest = root / sha(raw_manifest)
    dest.mkdir(exist_ok=False)
    for name, raw in (("official.json", official), ("independent.json", other),
                      ("manifest.json", raw_manifest)):
        with (dest / name).open("xb") as stream:
            stream.write(raw)
    return dest


def replay_candidate(path):
    path = Path(path)
    raw = (path / "manifest.json").read_bytes()
    m = decode(raw)
    a, b = ((path / name).read_bytes() for name in ("official.json", "independent.json"))
    first, _ = agree(a, b)
    expected = dict(FLAGS, schema="red-card-event-candidate-v1",
                    agreement="AGREED_UNVERIFIED", fixture_id=first["fixture_id"],
                    official_sha256=sha(a), independent_sha256=sha(b),
                    external_witness_verified=False, eligible_for_model_scoring=False)
    require(path.name == sha(raw) and raw == canonical(expected), "ARCHIVE_HASH_MISMATCH")
    return expected


def xg_windows(official, other, snapshots):
    """Three cumulative snapshots from one model: before, at, after dismissal.

    Exact card-clock boundary required. Post-card xG is for development only,
    never a feature in a prediction made at the card.
    """
    a, b = agree(official, other)
    require(isinstance(snapshots, list) and len(snapshots) == 3, "NEED_THREE_SNAPSHOTS")
    fixture = a["fixture_id"]
    first = snapshots[0]
    clocks, times, values = [], [], []
    for d in snapshots:
        require(d["fixture_id"] == fixture, "XG_FIXTURE_CONFLICT")
        for key in ("publisher_id", "xg_model"):
            require(ident(d[key]) == ident(first[key]), "XG_MODEL_OR_PROVIDER_CHANGED")
        c = d["clock_s"]
        require(type(c) is int and 0 <= c <= 5400, "BAD_XG_CLOCK")
        observed, captured = stamp(d["observed_utc"]), stamp(d["captured_utc"])
        require(stamp(a["kickoff_utc"]) <= observed <= captured, "BAD_XG_CAPTURE_TIME")
        clocks.append(c)
        times.append((observed, captured))
        values.append(tuple(number(d[key], 0, 30) for key in ("home_xg", "away_xg")))
    require(clocks[0] < clocks[1] == a["clock_s"] < clocks[2], "XG_CLOCK_BOUNDARY")
    require(times[0][0] < times[1][0] == stamp(a["event_utc"]) < times[2][0],
            "XG_TIME_BOUNDARY")
    require(times[0][1] <= times[1][0] and times[1][1] <= times[2][0],
            "XG_CAPTURE_AFTER_NEXT_WINDOW")
    require(min(clocks[1]-clocks[0], clocks[2]-clocks[1]) >= 300, "SHORT_WINDOW")
    require(all(values[i][k] <= values[i+1][k] for i in (0,1) for k in (0,1)),
            "XG_REVISED_OR_DECREASING")
    # Ordered as disadvantaged team, opponent.
    order = (0,1) if a["side"] == "HOME" else (1,0)
    return dict(FLAGS, fixture_id=fixture, xg_model=first["xg_model"],
                publisher_id=first["publisher_id"],
                event_utc=a["event_utc"],
                available_utc=max(times[2][1], stamp(a["captured_utc"]),
                                  stamp(b["captured_utc"])).isoformat(),
                pre_seconds=clocks[1]-clocks[0], post_seconds=clocks[2]-clocks[1],
                pre_xg=[values[1][k]-values[0][k] for k in order],
                post_xg=[values[2][k]-values[1][k] for k in order],
                development_only=True, source_authenticity_verified=False)


def fit_development(cases, cutoff):
    """Pooled exposure-adjusted xG ratios, descriptive and not causal.

    Replays normalized inputs instead of accepting caller-authored fit rows.
    No pseudocount, invented xG, zero-denominator imputation or promotion.
    """
    cutoff = stamp(cutoff)
    rows = [xg_windows(*case) for case in cases]
    seen = set()
    models = set()
    for row in rows:
        key = row["fixture_id"]
        require(key not in seen, "DUPLICATE_DEVELOPMENT_FIXTURE")
        seen.add(key)
        require(stamp(row["available_utc"]) < cutoff, "DEVELOPMENT_TIME_LEAKAGE")
        models.add((row["publisher_id"], row["xg_model"]))
    require(len(models) <= 1, "MIXED_XG_MODELS")
    out = dict(FLAGS, development_count=len(rows), cutoff=cutoff.isoformat(),
               development_fixture_ids=sorted(seen), ratios=None,
               model_calibration_verified=False, causal_effect_verified=False)
    if not rows:
        return dict(out, reason="NO_DEVELOPMENT_ROWS")
    pre_s = sum(row["pre_seconds"] for row in rows)
    post_s = sum(row["post_seconds"] for row in rows)
    pre = [sum(row["pre_xg"][k] for row in rows) / pre_s for k in (0,1)]
    post = [sum(row["post_xg"][k] for row in rows) / post_s for k in (0,1)]
    if min(pre) <= 0:
        return dict(out, reason="ZERO_PRE_XG_RATE")
    return dict(out, ratios=[post[k]/pre[k] for k in (0,1)],
                reason="DESCRIPTIVE_XG_RATIOS_ONLY")


def prospective_intake(cases, *, cutoff, development_fixture_ids):
    """Validate prospective candidate structure, never certify a true cohort.

    Each tuple is (official bytes, independent bytes, prediction bytes,
    result bytes). Source-specific witness and FT verifier integration
    is required before ANY candidate can be scored as authenticated.
    """
    cutoff = stamp(cutoff)
    seen = set(development_fixture_ids)
    candidate_count = 0
    for official, other, prediction, result in cases:
        a, b = agree(official, other)
        p, f = decode(prediction), decode(result)
        fixture = a["fixture_id"]
        require(fixture not in seen, "DUPLICATE_OR_DEVELOPMENT_FIXTURE")
        seen.add(fixture)
        require(p["fixture_id"] == f["fixture_id"] == fixture, "FIXTURE_CONFLICT")
        require(p["official_sha256"] == sha(official) and
                p["independent_sha256"] == sha(other), "PREDICTION_EVENT_HASH_CONFLICT")
        ident(p["baseline_model"]); ident(p["challenger_model"])
        require(p["baseline_model"] != p["challenger_model"], "SAME_MODEL")
        require(stamp(p["training_cutoff_utc"]) == cutoff <
                stamp(a["kickoff_utc"]) <= stamp(a["event_utc"]) <=
                max(stamp(a["captured_utc"]), stamp(b["captured_utc"])) <=
                stamp(p["prediction_utc"]) < stamp(f["final_utc"]) <=
                stamp(f["captured_utc"]), "PROSPECTIVE_TIME_LEAKAGE")
        for key in ("baseline", "challenger"):
            v = p[key]
            require(isinstance(v, list) and len(v) == 3, "BAD_PROBABILITY_VECTOR")
            require(abs(sum(number(x,0,1) for x in v)-1) <= 1e-6, "BAD_PROBABILITY_SUM")
        final = score(f["score"])
        require(f["status"] == "FT" and all(x >= y for x,y in zip(final, a["score"])),
                "BAD_FINAL_SCORE")
        candidate_count += 1
    return dict(FLAGS, candidate_count=candidate_count, verified_count=0,
                true_prospective_count=0, external_witness_verified=False,
                confidence_interval=None, log_loss=None,
                reason="EXTERNAL_CAPTURE_WITNESS_AND_RESULT_VERIFIER_REQUIRED")
