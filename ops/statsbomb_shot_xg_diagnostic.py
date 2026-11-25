"""Offline StatsBomb shot-quality diagnostics; never a prematch forecast.

Reuse the pinned World Cup manifest and byte checks from xT research.
Regulation shots only, penalties separately, own goals not shot goals.
No source acquisition, commercial rights grant, model fit or EV.
"""
import json
import math
from hashlib import sha256
from ops.xt_chronological_research import validate_manifest, verify_all_historical_sources


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[k] = v
    return out


def _bad_constant(value):
    raise ValueError("NONFINITE_JSON")


def summarize_shots(raw, rec):
    # Even direct callers must supply matching length, hash and record count.
    spec = rec["events"]
    if type(raw) is not bytes or not 0 < len(raw) <= 8_000_000 or len(raw) != spec["bytes"] or sha256(raw).hexdigest() != spec["sha256"]:
        raise ValueError("EVENT_BYTES_MISMATCH")
    events = json.loads(raw, object_pairs_hook=_unique, parse_constant=_bad_constant)
    if type(events) is not list or not 0 < len(events) <= 20_000 or len(events) != spec["records"]:
        raise ValueError("EVENT_COUNT_MISMATCH")
    ids = (rec["home_team_id"], rec["away_team_id"])
    if any(type(t) is not int or t <= 0 for t in ids) or ids[0] == ids[1]:
        raise ValueError("INVALID_TEAM_IDS")
    buckets = {t: {"all": [], "non_penalty": []} for t in ids}
    seen = set()
    excluded_shots = 0
    for event in events:
        if type(event) is not dict:
            raise ValueError("INVALID_EVENT")
        eid = event.get("id")
        if type(eid) is not str or not eid.strip() or eid in seen:
            raise ValueError("INVALID_OR_DUPLICATE_EVENT_ID")
        seen.add(eid)
        kind = event.get("type")
        if type(kind) is not dict or type(kind.get("name")) is not str:
            raise ValueError("INVALID_EVENT_TYPE")
        if kind["name"] != "Shot":
            continue
        period = event.get("period")
        if type(period) is not int or period not in (1, 2, 3, 4, 5):
            raise ValueError("INVALID_SHOT_PERIOD")
        if period not in (1, 2):
            excluded_shots += 1
            continue
        team, shot = event.get("team"), event.get("shot")
        if type(team) is not dict or type(team.get("id")) is not int or team["id"] not in buckets or type(shot) is not dict:
            raise ValueError("INVALID_SHOT_TEAM_OR_DATA")
        xg = shot.get("statsbomb_xg")
        if type(xg) not in (int, float) or not 0 <= xg <= 1 or not math.isfinite(xg):
            raise ValueError("MISSING_OR_INVALID_PROVIDER_XG")
        outcome, shot_type = shot.get("outcome"), shot.get("type")
        if any(type(v) is not dict or type(v.get("name")) is not str or not v["name"].strip() for v in (outcome, shot_type)):
            raise ValueError("INVALID_SHOT_LABEL")
        result = (float(xg), int(outcome["name"] == "Goal"))
        buckets[team["id"]]["all"].append(result)
        if shot_type["name"] != "Penalty":
            buckets[team["id"]]["non_penalty"].append(result)

    def metrics(items):
        n = len(items)
        xg = math.fsum(x for x, _ in items)
        goals = sum(y for _, y in items)
        return {"shots": n, "xg": xg, "shot_goals": goals,
                "goals_minus_xg": goals - xg,
                "xg_per_shot": xg/n if n else None,
                "goals_per_shot": goals/n if n else None,
                "shot_brier": math.fsum((x-y)**2 for x,y in items)/n if n else None}
    return {"match_id": rec["match_id"], "excluded_extra_time_or_shootout_shots": excluded_shots,
            "teams": {str(t): {"attack": {k: metrics(v) for k,v in buckets[t].items()},
                "defense": {k: metrics(v) for k,v in buckets[ids[1] if t == ids[0] else ids[0]].items()}}
                for t in ids}}


def audit_local(root, manifest):
    train, evaluation = validate_manifest(manifest)
    frozen = verify_all_historical_sources(root, manifest)
    return {"status": "HOLD", "production_recommendations": "DISABLED",
            "source": "StatsBomb Open Data", "source_rights_independently_verified": False,
            "prospective_samples": 0, "model_promoted": False, "positive_ev_verified": False,
            "postmatch_diagnostics_only": True,
            "training": [summarize_shots(frozen[r["match_id"]]["events"], r) for r in train],
            "evaluation": [summarize_shots(frozen[r["match_id"]]["events"], r) for r in evaluation]}
