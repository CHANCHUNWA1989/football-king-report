"""Offline StatsBomb historical shot input quality checks.

No network, data redistribution, live xG, player strength estimation, or
prediction adjustment. Caller metadata and file hashes are not authentication.
Only process lawfully obtained local files for private research.
"""
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

SCHEMA = "football-king-dhe-historical-shot-input-v1"
MAX_BYTES = 20_000_000
MAX_EVENTS = 20000
SHA = re.compile(r"[0-9a-f]{64}")


def _utc(v):
    if type(v) is not str or len(v) > 80:
        raise ValueError("BAD_TIME")
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return dt.astimezone(timezone.utc)


def _id(v):
    if type(v) is not int or not 0 < v < 10**15:
        raise ValueError("BAD_NATIVE_ID")
    return v


def _unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("NONFINITE_JSON")


def _decode(raw, maximum):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise ValueError("FILE_SIZE_OR_TYPE")
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)


def inspect(events_raw, match, *, as_of_utc):
    """Check a declared historical match/event artifact.

    Match metadata must explicitly bind the native ID, teams, source path,
    captured UTC, expected event digest, and recorded regulation end.
    No external authentication of these claims is performed.
    """
    out = {"schema": SCHEMA, "status": "HOLD",
           "production_recommendations": "DISABLED", "research_only": True,
           "source": "StatsBomb Open Data", "historical_only": True,
           "source_authenticated": False, "artifact_witness_verified": False,
           "complete_regulation_events_authenticated": False,
           "live_xg_verified": False, "player_value_calibrated": False,
           "model_inputs_enabled": False, "qualifies_for_betting": False,
           "positive_expected_value_verified": False, "public_redistribution_allowed": False,
           "true_forward_sample_count": 0, "private_features": None}
    try:
        if type(match) is not dict or match.get("source") != "statsbomb_open_data":
            raise ValueError("BAD_SOURCE_METADATA")
        mid,h,a = (_id(match[k]) for k in ("match_id","home_team_id","away_team_id"))
        if h == a or match.get("event_path") != f"data/events/{mid}.json":
            raise ValueError("MATCH_BINDING_MISMATCH")
        if match.get("status") != "FINISHED_REGULATION_CLAIM":
            raise ValueError("NOT_REGULATION_HISTORY")
        ko,end,captured,now = (_utc(x) for x in (match["kickoff_utc"],
                                  match["regulation_end_utc"],match["captured_utc"],as_of_utc))
        if not ko+timedelta(minutes=90) <= end <= ko+timedelta(hours=4):
            raise ValueError("BAD_REGULATION_END")
        if not end <= captured <= now or end >= now:
            raise ValueError("FUTURE_OR_INCOMPLETE_HISTORY")
        if type(events_raw) is not bytes or not 0 < len(events_raw) <= MAX_BYTES:
            raise ValueError("FILE_SIZE_OR_TYPE")
        digest = hashlib.sha256(events_raw).hexdigest()
        wanted = match.get("events_sha256")
        if type(wanted) is not str or not SHA.fullmatch(wanted) or digest != wanted:
            raise ValueError("EVENT_DIGEST_MISMATCH")
        events = _decode(events_raw, MAX_BYTES)
        if type(events) is not list or not 0 < len(events) <= MAX_EVENTS:
            raise ValueError("BAD_EVENT_COLLECTION")
        seen,indices,ends = set(),set(),set()
        team_xg = {h:[],a:[]}
        player_xg = defaultdict(list)
        player_team = {}
        shots = {h:0,a:0}
        for row in events:
            if type(row) is not dict:
                raise ValueError("BAD_EVENT")
            event_id = row.get("id")
            index,period = row.get("index"),row.get("period")
            if (type(event_id) is not str or not 1 <= len(event_id) <= 128
                    or event_id in seen or type(index) is not int or index <= 0
                    or index in indices or type(period) is not int or period not in (1,2,3,4,5)):
                raise ValueError("DUPLICATE_OR_INVALID_EVENT_IDENTITY")
            seen.add(event_id)
            indices.add(index)
            if "match_id" in row and _id(row["match_id"]) != mid:
                raise ValueError("EVENT_MATCH_ID_MISMATCH")
            kind = row.get("type")
            if type(kind) is not dict or type(kind.get("name")) is not str:
                raise ValueError("BAD_EVENT_TYPE")
            if period not in (1,2):
                continue
            if kind["name"] == "Half End":
                ends.add(period)
            # Do not silently discard malformed shots or accept shot payloads
            # disguised as another type. Penalty shootouts are excluded above.
            if kind["name"] != "Shot":
                if "shot" in row:
                    raise ValueError("SHOT_TYPE_CONFLICT")
                continue
            team = _id(row["team"]["id"])
            player = _id(row["player"]["id"])
            if team not in team_xg or player_team.setdefault(player,team) != team:
                raise ValueError("SHOT_TEAM_IDENTITY_CONFLICT")
            xg = row["shot"]["statsbomb_xg"]
            if type(xg) not in (int,float) or not math.isfinite(xg) or not 0 <= xg <= 1:
                raise ValueError("MISSING_OR_INVALID_SHOT_XG")
            team_xg[team].append(xg)
            player_xg[player].append(xg)
            shots[team]+=1
        if ends != {1,2} or len(indices) != max(indices):
            raise ValueError("INCOMPLETE_EVENT_SEQUENCE_CLAIM")
        # Sum provider shot-xG only; this is not a measure of total player
        # ability, xA, minutes, defending, or calibrated next-match rates.
        hx,ax = math.fsum(team_xg[h]),math.fsum(team_xg[a])
        out.update(reason="STRUCTURAL_HISTORICAL_SHOT_FEATURES_PRIVATE_ONLY",
                   event_sha256=digest,event_count=len(events),
                   native_match_id=mid,
                   private_features={"home_shots":shots[h],"away_shots":shots[a],
                      "home_shot_xg":hx,"away_shot_xg":ax,"home_shot_xga":ax,"away_shot_xga":hx,
                      "players":[{"player_id":p,"team_id":player_team[p],
                                  "shots":len(v),"shot_xg":math.fsum(v)}
                                 for p,v in sorted(player_xg.items())]},
                   extra_time_and_shootouts_excluded=True,
                   historical_snapshot_not_proven_available_before_past_predictions=True)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
        allowed = {"BAD_SOURCE_METADATA","MATCH_BINDING_MISMATCH","NOT_REGULATION_HISTORY",
                   "BAD_REGULATION_END","FUTURE_OR_INCOMPLETE_HISTORY","FILE_SIZE_OR_TYPE",
                   "EVENT_DIGEST_MISMATCH","BAD_EVENT_COLLECTION","BAD_EVENT",
                   "DUPLICATE_OR_INVALID_EVENT_IDENTITY","EVENT_MATCH_ID_MISMATCH",
                   "BAD_EVENT_TYPE","SHOT_TYPE_CONFLICT","SHOT_TEAM_IDENTITY_CONFLICT",
                   "MISSING_OR_INVALID_SHOT_XG","INCOMPLETE_EVENT_SEQUENCE_CLAIM",
                   "DUPLICATE_JSON_KEY","NONFINITE_JSON"}
        out["reason"] = str(exc) if str(exc) in allowed else "INVALID_HISTORICAL_INPUT"
    return out


def rest_interval(previous_end_utc, next_kickoff_utc, *, observed_utc, as_of_utc):
    """Compute declared rest interval, not fatigue or a complete schedule."""
    try:
        end,ko,observed,now = map(_utc,(previous_end_utc,next_kickoff_utc,observed_utc,as_of_utc))
        if not end <= observed <= now < ko or ko-end > timedelta(days=60):
            raise ValueError("INVALID_REST_CHRONOLOGY")
        return {"status":"HOLD","rest_hours":(ko-end).total_seconds()/3600,
                "schedule_completeness_verified":False,"fatigue_effect_calibrated":False,
                "production_recommendations":"DISABLED"}
    except (ValueError,TypeError,OverflowError):
        return {"status":"HOLD","rest_hours":None,"schedule_completeness_verified":False,
                "fatigue_effect_calibrated":False,"production_recommendations":"DISABLED"}
