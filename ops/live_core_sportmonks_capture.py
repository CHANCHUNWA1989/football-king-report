"""Sportmonks v3 single-fixture captured payload -> observation claim.
Docs: /v3/tutorials-and-guides/tutorials/includes/{scores,periods,events}
and /v3/definitions/{states,types/events}. No fetch or account entitlement.
Conservatively hold any VAR or rescinded incident rather than infer revisions.
"""
import hashlib
import json
from vnext_direct_transport_offline import unique_object,reject_constant
from live_core_real_observations import evidence
from live_core_provider_evidence import normalize,run,MAX_BYTES
from live_snapshot_adapter import hold


def parse(raw,mapping,*,captured,received,observed_claim,now):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES:
        raise ValueError("CAPTURE_SIZE")
    if any(type(v) is not int for v in (captured,received,observed_claim,now)) or not 0<observed_claim<=captured<=received<=now or now-observed_claim>90:
        raise ValueError("CAPTURE_CLOCK")
    if type(mapping) is not dict or set(mapping)!={"fixture_id","provider_id","home_id","away_id","kickoff_epoch"}:
        raise ValueError("CROSSWALK_SCHEMA")
    if any(type(mapping[k]) is not int or mapping[k]<=0 for k in ("provider_id","home_id","away_id","kickoff_epoch")) or mapping["home_id"]==mapping["away_id"]:
        raise ValueError("CROSSWALK_ID")
    payload=json.loads(raw.decode("utf-8"),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if type(payload) is not dict or payload.get("error") or payload.get("errors"):
        raise ValueError("PROVIDER_ERROR")
    row=payload["data"]
    if row["id"]!=mapping["provider_id"] or row["starting_at_timestamp"]!=mapping["kickoff_epoch"]:
        raise ValueError("FIXTURE_ID")
    participants=row["participants"]
    if type(participants) is not list or len(participants)!=2:
        raise ValueError("PARTICIPANTS")
    teams={p["meta"]["location"]:p["id"] for p in participants}
    if teams!={"home":mapping["home_id"],"away":mapping["away_id"]}:
        raise ValueError("TEAM_IDENTITY")
    phase={2:("FIRST_HALF",1),6:("SECOND_HALF",2)}.get(row["state_id"])
    if phase is None:
        raise ValueError("UNSUPPORTED_STATE")
    periods=row["periods"]
    if type(periods) is not list or not 1<=len(periods)<=10:
        raise ValueError("PERIODS")
    active=[p for p in periods if p["ticking"] is True]
    if len(active)!=1 or active[0]["type_id"]!=phase[1]:
        raise ValueError("PERIOD_CONFLICT")
    minute=active[0]["minutes"]
    scores=row["scores"]
    if type(scores) is not list or len(scores)>30:
        raise ValueError("SCORES")
    current={}
    for s in scores:
        if s["description"]!="CURRENT":
            continue
        side=s["score"]["participant"]
        if side not in teams or side in current or s["participant_id"]!=teams[side]:
            raise ValueError("SCORE_IDENTITY")
        current[side]=s["score"]["goals"]
    if set(current)!=set(teams):
        raise ValueError("CURRENT_SCORE_MISSING")
    events=row["events"]
    if type(events) is not list or len(events)>200:
        raise ValueError("EVENTS")
    dismissed={k:set() for k in teams.values()}
    ids=set()
    for e in events:
        eid=e["id"]
        if type(eid) is not int or eid<=0 or eid in ids:
            raise ValueError("EVENT_ID")
        ids.add(eid)
        # Strict allowlist; unknown types or rescissions require review.
        t=e["type_id"]
        if type(t) is not int or t not in (14,15,16,17,18,19,20,21) or e.get("rescinded") not in (None,False):
            raise ValueError("EVENT_CORRECTION_REVIEW")
        if t not in (20,21):
            continue
        team,player,em=e["participant_id"],e["player_id"],e["minute"]
        if team not in dismissed or type(player) is not int or player<=0 or type(em) is not int or not 0<=em<=minute or e.get("extra_minute") not in (None,0):
            raise ValueError("RED_EVENT")
        dismissed[team].add(player)
    state=dict(fixture_id=mapping["fixture_id"],origin="sportmonks",observed=observed_claim,
               received=received,minute=minute,home=current["home"],away=current["away"],
               red_home=len(dismissed[teams["home"]]),red_away=len(dismissed[teams["away"]]),
               phase=phase[0])
    out=dict(state=state,url="https://api.sportmonks.com/v3/football/fixtures",
             payload_sha256=hashlib.sha256(raw).hexdigest())
    evidence(out,now)
    return out


def dual_run(primary_raw,primary_mapping,secondary_raw,secondary_mapping,*,primary_clock,
             secondary_clock,now,prematch,markets,quotes=None):
    """Raw bytes from both sources; caller must attest rights separately."""
    try:
        from datetime import datetime
        if primary_mapping["fixture_id"]!=secondary_mapping["fixture_id"]:
            raise ValueError("CANONICAL_FIXTURE")
        dt=datetime.fromisoformat(primary_mapping["kickoff_utc"].replace("Z","+00:00"))
        if dt.tzinfo is None or dt.timestamp()!=secondary_mapping["kickoff_epoch"]:
            raise ValueError("KICKOFF_CROSSWALK")
        second=parse(secondary_raw,secondary_mapping,now=now,**secondary_clock)
        result=run(primary_raw,primary_mapping,now=now,secondary=second,
                   prematch=prematch,markets=markets,quotes=quotes,**primary_clock)
        if result.get("research_status")=="RESEARCH_ONLY":
            result["secondary_payload_digest"]=second["payload_sha256"]
            result["two_raw_payloads_parsed"]=True
        return result
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("DUAL_CAPTURE_REJECTED")
