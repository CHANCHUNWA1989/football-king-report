"""Structural correction review only. Never resume forecasts or authenticate sources."""
import hashlib
import hmac
import json
from datetime import datetime
from live_snapshot_adapter import check, hold, valid

EVENT_FIELDS = {"origin","fixture_id","kind","side","event_ref","observed","received"}
STATE = ("fixture_id","minute","home","away","red_home","red_away","phase")
COLUMNS = ("home","away","red_home","red_away")
DELTAS = {("GOAL_CANCELLED","HOME"):"home",("GOAL_CANCELLED","AWAY"):"away",
          ("RED_RESCINDED","HOME"):"red_home",("RED_RESCINDED","AWAY"):"red_away"}

def review_digest(package):
    if type(package) is not dict or set(package) != {"envelope","events"}:
        raise ValueError("INVALID_PACKAGE")
    data = json.dumps(package,sort_keys=True,separators=(",",":"),ensure_ascii=True,
                      allow_nan=False).encode("ascii")
    if len(data)>65536:
        raise ValueError("PACKAGE_TOO_LARGE")
    return hashlib.sha256(b"football-king/correction-review/v1\x00"+data).hexdigest()

def review_correction(package, expected_digest, now):
    try:
        digest=review_digest(package)
        if (type(expected_digest) is not str or len(expected_digest)!=64
                or not expected_digest.isascii() or not hmac.compare_digest(digest,expected_digest)):
            return hold("CORRECTION_COMMITMENT_MISMATCH")
        env=package["envelope"]
        if (type(env) is not dict or set(env)!={"a","b","model","decision_epoch","previous_a","previous_b"}
                or type(now) is not int or type(env["decision_epoch"]) is not int or now!=env["decision_epoch"]):
            return hold("INVALID_CORRECTION_ENVELOPE")
        a,b,model=env["a"],env["b"],env["model"]
        reason=check(a,b,model,now)
        if reason!="CONSISTENT":
            return hold(reason)
        pa,pb=env["previous_a"],env["previous_b"]
        if not valid(pa) or not valid(pb) or any(pa[k]!=pb[k] for k in STATE):
            return hold("CORRECTION_HISTORY_CONFLICT")
        if abs(pa["observed"]-pb["observed"])>30:
            return hold("CORRECTION_HISTORY_UNSYNCED")
        kickoff=datetime.fromisoformat(model["kickoff_utc"].replace("Z","+00:00"))
        if kickoff.tzinfo is None or kickoff.utcoffset() is None:
            return hold("INVALID_KICKOFF")
        ko=kickoff.timestamp()
        for current,prior in ((a,pa),(b,pb)):
            if (current["origin"]!=prior["origin"] or current["fixture_id"]!=prior["fixture_id"]
                    or not ko<=prior["observed"]<current["observed"]
                    or not prior["received"]<current["received"] or prior["minute"]>current["minute"]):
                return hold("CORRECTION_HISTORY_REPLAY")
        events=package["events"]
        if type(events) is not list or len(events)!=2:
            return hold("TWO_CORRECTION_CLAIMS_REQUIRED")
        if any(type(e) is not dict or set(e)!=EVENT_FIELDS for e in events):
            return hold("INVALID_CORRECTION_EVENT")
        by_origin={}
        for e in events:
            if any(type(e[k]) is not str or not 1<=len(e[k])<=128 or not e[k].isprintable()
                   or e[k].strip()!=e[k] for k in ("origin","fixture_id","kind","side","event_ref")):
                return hold("INVALID_CORRECTION_EVENT")
            if e["origin"] in by_origin:
                return hold("DUPLICATE_CORRECTION_ORIGIN")
            by_origin[e["origin"]]=e
        if set(by_origin)!={a["origin"],b["origin"]}:
            return hold("CORRECTION_ORIGIN_MISMATCH")
        if any(events[0][k]!=events[1][k] for k in ("kind","side","fixture_id")):
            return hold("CORRECTION_EVENT_CONFLICT")
        column=DELTAS.get((events[0]["kind"],events[0]["side"]))
        if column is None:
            return hold("UNSUPPORTED_CORRECTION")
        for current,prior in ((a,pa),(b,pb)):
            e=by_origin[current["origin"]]
            if (e["fixture_id"]!=current["fixture_id"] or type(e["observed"]) is not int
                    or type(e["received"]) is not int
                    or not prior["observed"]<e["observed"]<=current["observed"]
                    or not e["observed"]<=e["received"]<=current["received"]<=now):
                return hold("CORRECTION_CLOCK_OR_FIXTURE_MISMATCH")
            if any(current[k]-prior[k]!=(-1 if k==column else 0) for k in COLUMNS):
                return hold("CORRECTION_DELTA_MISMATCH")
        out=hold("CONSISTENT_CORRECTION_CLAIMS_PENDING_REVIEW")
        out.update(correction_review_only=True,correction_digest_unattested=digest,
                   correction_authenticated=False,forecast_resume_allowed=False)
        return out
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_CORRECTION_INPUT")

def review_stoppage(elapsed_seconds, announced_minimum_minutes):
    """Second-half stoppage diagnostic, NOT a full-time inference or time forecast."""
    if type(elapsed_seconds) is not int or not 0<=elapsed_seconds<=3600:
        return hold("INVALID_STOPPAGE_CLOCK")
    if announced_minimum_minutes is None:
        return hold("STOPPAGE_MINIMUM_UNKNOWN")
    if type(announced_minimum_minutes) is not int or not 0<=announced_minimum_minutes<=60:
        return hold("INVALID_ANNOUNCED_MINIMUM")
    out=hold("STOPPAGE_END_UNCONFIRMED")
    out.update(claimed_minimum_remaining_seconds=max(0,60*announced_minimum_minutes-elapsed_seconds),
               final_whistle_verified=False,forecast_resume_allowed=False)
    return out
