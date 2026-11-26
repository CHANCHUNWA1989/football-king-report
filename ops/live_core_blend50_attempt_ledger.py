"""Local append-style attempt ledger for the locked blend50 research protocol.

Hash chains and caller clocks do not establish independent attestation, complete
fixture discovery, or write-once storage. No production or betting admission.
"""
import argparse
import json
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from live_core_blend50_forward_seal import seal,digest,instant,fields,identifier,PROTOCOL,START,END,LEAGUES
from live_core_blend50_forward_settlement import settle,aggregate
from research_strict_json import unique_object,reject_constant

SCHEMA="FK-BLEND50-ATTEMPTS-V1"
GENESIS="0"*64
MAX_EVENTS=2000
MAX_BYTES=64_000_000
CAPTURE_REASONS=frozenset(("SOURCE_UNAVAILABLE","FIXTURE_CONFLICT","HISTORY_INCOMPLETE","CAPTURE_ERROR"))
RESULT_REASONS=frozenset(("RESULT_UNAVAILABLE","RESULT_CONFLICT","IDENTITY_CONFLICT","SETTLEMENT_ERROR"))

def key_for(f):
    fields(f,"league home away kickoff_utc")
    if f["league"] not in LEAGUES:raise ValueError("LEAGUE_SCOPE")
    h,a=identifier(f["home"]),identifier(f["away"])
    if h==a:raise ValueError("SAME_TEAM")
    ko=instant(f["kickoff_utc"])
    if not START<ko<END:raise ValueError("FIXTURE_WINDOW")
    return digest([f["league"],h,a,ko.isoformat()])

def empty():
    return {"schema":SCHEMA,"protocol":PROTOCOL,"events":[]}

def check_prefix_checkpoint(checkpoint,events):
    # A separately retained caller checkpoint may describe an older prefix.
    # Full chain validation must run before this check; a matching prefix
    # establishes local continuity, not an externally attested timestamp.
    fields(checkpoint,"event_count head_sha256")
    n,head=checkpoint["event_count"],checkpoint["head_sha256"]
    if (type(n) is not int or not 0<=n<=MAX_EVENTS
            or type(head) is not str or len(head)!=64
            or any(c not in "0123456789abcdef" for c in head)):
        raise ValueError("INVALID_PREFIX_CHECKPOINT")
    if n>len(events):raise ValueError("PREFIX_TRUNCATED")
    actual=events[n-1]["sha256"] if n else GENESIS
    if actual!=head:raise ValueError("PREFIX_FORK_OR_REWRITE")
    return n

def audit(doc,*,now=None,expected_head=None,prefix_checkpoint=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    now=now.astimezone(timezone.utc)
    fields(doc,"schema protocol events")
    if doc["schema"]!=SCHEMA or doc["protocol"]!=PROTOCOL:raise ValueError("LEDGER_SCOPE")
    events=doc["events"]
    if type(events) is not list or len(events)>MAX_EVENTS:raise ValueError("EVENT_SCOPE")
    prev=GENESIS;last=START;fixtures={};native=set();cases=[];reasons=Counter()
    for i,e in enumerate(events,1):
        fields(e,"seq prev_sha256 observed_utc kind fixture_key payload sha256")
        if type(e["seq"]) is not int or e["seq"]!=i or e["prev_sha256"]!=prev:raise ValueError("CHAIN_SEQUENCE")
        actual=digest({k:v for k,v in e.items() if k!="sha256"})
        if actual!=e["sha256"]:raise ValueError("CHAIN_DIGEST")
        at=instant(e["observed_utc"])
        if not last<=at<=now:raise ValueError("EVENT_CLOCK")
        prev=actual;last=at
        key=e["fixture_key"];kind=e["kind"];p=e["payload"]
        if kind=="REGISTER":
            if key!=key_for(p) or key in fixtures:raise ValueError("REGISTRATION_ID")
            ko=instant(p["kickoff_utc"])
            if not START<=at<=ko-timedelta(minutes=10):raise ValueError("REGISTRATION_TIME")
            fixtures[key]={"fixture":p,"ko":ko,"capture_failures":0,"result_failures":0,
                           "original":None,"forecast":None,"settled":False}
            continue
        if key not in fixtures:raise ValueError("UNREGISTERED_FIXTURE")
        f=fixtures[key];ko=f["ko"]
        if f["settled"]:raise ValueError("AFTER_SETTLEMENT")
        if kind in ("CAPTURE","CAPTURE_FAILED"):
            if f["forecast"] is not None:raise ValueError("FORECAST_ALREADY_SEALED")
            if not timedelta(minutes=10)<=ko-at<=timedelta(hours=24):raise ValueError("CAPTURE_WINDOW")
            if kind=="CAPTURE_FAILED":
                fields(p,"reason")
                if p["reason"] not in CAPTURE_REASONS:raise ValueError("FAILURE_REASON")
                f["capture_failures"]+=1;reasons[p["reason"]]+=1;continue
            fields(p,"original forecast")
            rebuilt=seal(p["original"],now=at)
            if digest(rebuilt)!=digest(p["forecast"]) or rebuilt["record"]["fixture_key"]!=key:
                raise ValueError("CAPTURE_REPLAY_MISMATCH")
            ids={(s["provider"].casefold(),s["fixture_id"]) for s in p["original"]["fixture"]["sources"]}
            if native&ids:raise ValueError("REUSED_NATIVE_ID")
            native.update(ids)
            f["original"]=p["original"];f["forecast"]=p["forecast"]
        elif kind in ("SETTLE","SETTLE_FAILED"):
            if f["forecast"] is None or at<ko+timedelta(minutes=120):raise ValueError("SETTLEMENT_WINDOW")
            if kind=="SETTLE_FAILED":
                fields(p,"reason")
                if p["reason"] not in RESULT_REASONS:raise ValueError("FAILURE_REASON")
                f["result_failures"]+=1;reasons[p["reason"]]+=1;continue
            fields(p,"results")
            settle(f["original"],f["forecast"],p["results"],now=at)
            cases.append({"original":f["original"],"forecast":f["forecast"],"results":p["results"]})
            f["settled"]=True
        else:raise ValueError("UNKNOWN_EVENT")
    if expected_head is not None and prev!=expected_head:raise ValueError("EXPECTED_HEAD_MISMATCH")
    prefix_n=(check_prefix_checkpoint(prefix_checkpoint,events)
              if prefix_checkpoint is not None else None)
    counts=Counter();by_league=defaultdict(Counter)
    for f in fixtures.values():
        if f["settled"]:state="SETTLED_LOCAL"
        elif f["forecast"] is not None:
            state="RESULT_DUE_UNSETTLED" if now>=f["ko"]+timedelta(minutes=120) else "SEALED_PENDING_RESULT"
        else:
            state="CAPTURE_MISSED" if now>f["ko"]-timedelta(minutes=10) else "REGISTERED_PENDING_CAPTURE"
        counts[state]+=1;by_league[f["fixture"]["league"]][state]+=1
    states=("SETTLED_LOCAL","RESULT_DUE_UNSETTLED","SEALED_PENDING_RESULT","CAPTURE_MISSED","REGISTERED_PENDING_CAPTURE")
    if sum(counts.values())!=len(fixtures):raise ValueError("DENOMINATOR_MISMATCH")
    scoring=aggregate(cases,now=now)
    if scoring["recorded_local_cases"]!=counts["SETTLED_LOCAL"]:raise ValueError("SCORE_COUNT_MISMATCH")
    return {"schema":SCHEMA,"protocol":PROTOCOL,"checked_utc":now.isoformat(),"head_sha256":prev,
            "event_count":len(events),"registered_fixture_count":len(fixtures),
            "states":{s:counts[s] for s in states},
            "by_league":{k:{s:by_league[k][s] for s in states} for k in LEAGUES},
            "capture_failure_events":sum(f["capture_failures"] for f in fixtures.values()),
            "settlement_failure_events":sum(f["result_failures"] for f in fixtures.values()),
            "caller_reported_failure_reasons":dict(reasons),"local_scoring":scoring,
            "expected_head_checked":expected_head is not None,
            "caller_prefix_checkpoint_checked":prefix_n is not None,
            "caller_prefix_event_count":prefix_n,
            "events_after_caller_prefix":len(events)-prefix_n if prefix_n is not None else None,
            "checkpoint_externally_authenticated":False,
            "complete_attempt_denominator_verified":False,
            "write_once_storage_verified":False,"external_timestamp_attested":False,
            "authenticated_forward_samples":0,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

def append(doc,event,*,now=None,expected_head):
    # Require caller checkpoint, check old prefix, return a new document.
    now=now or datetime.now(timezone.utc)
    if type(expected_head) is not str or len(expected_head)!=64:raise ValueError("CHECKPOINT_REQUIRED")
    before=audit(doc,now=now,expected_head=expected_head)
    fields(event,"observed_utc kind fixture_key payload")
    e={**event,"seq":before["event_count"]+1,"prev_sha256":before["head_sha256"]}
    e["sha256"]=digest(e)
    new={**doc,"events":[*doc["events"],e]}
    audit(new,now=now)
    return new

def load(path):
    with Path(path).open("rb") as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError("INPUT_SIZE")
    return json.loads(raw.decode("utf-8"),object_pairs_hook=unique_object,parse_constant=reject_constant)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True);p.add_argument("--output",required=True)
    p.add_argument("--event");p.add_argument("--expected-head")
    p.add_argument("--prefix-checkpoint",help="Separately retained caller JSON checkpoint, audit only")
    a=p.parse_args()
    if a.event and a.prefix_checkpoint:p.error("--prefix-checkpoint is audit only")
    doc=load(a.input)
    if a.event:
        result=append(doc,load(a.event),expected_head=a.expected_head)
    else:
        checkpoint=load(a.prefix_checkpoint) if a.prefix_checkpoint else None
        if a.prefix_checkpoint and checkpoint is None:raise ValueError("INVALID_PREFIX_CHECKPOINT")
        result=audit(doc,expected_head=a.expected_head,prefix_checkpoint=checkpoint)
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(result,f,sort_keys=True,allow_nan=False)
if __name__=="__main__":main()
