"""Private unified market routing; never publishes or replaces a public feed.

Recompute components from original local inputs, keep providers separate, and
abstain on recorded identity/clock/probability disagreement. No network.
"""
from collections import Counter,defaultdict
from datetime import timedelta
from .research_candidate_gap_v6 import stamp
from .research_prospective_fusion_v38 import REGISTRATION_NOT_BEFORE
from .research_prospective_market_v41 import audit
from .research_private_propline_v43 import private_components
from .research_missing_fixture_discovery_v16 import identity

MAX_PRIVATE_BATCHES=6
MAX_PROB_DELTA=.10
MAX_UPDATE_SKEW=timedelta(minutes=20)

def route(primary_raw,private_batches,*,as_of):
    now=stamp(as_of)
    if not isinstance(private_batches,list) or len(private_batches)>MAX_PRIVATE_BATCHES:
        raise ValueError("invalid private batch roster")
    primary=[];backup=[];source_states=Counter();leagues=set()
    if primary_raw is not None:
        report=audit(primary_raw,as_of=as_of,include_components=True)
        primary=report["components"]
        source_states.update({"PRIMARY_"+k:v for k,v in report["states"].items()})
    for batch in private_batches:
        if not isinstance(batch,dict) or set(batch)!={"raw","league","captured_utc"}:
            raise ValueError("invalid private batch")
        league=batch["league"]
        if league in leagues:raise ValueError("duplicate private league batch")
        leagues.add(league)
        # Stale input is not an eligible route; malformed input fails the audit.
        age=now-stamp(batch["captured_utc"])
        if age<timedelta(0):raise ValueError("future private capture")
        if age>timedelta(minutes=20):
            source_states["PRIVATE_STALE_BATCH"]+=1;continue
        components,report=private_components(batch["raw"],league=league,
                    captured_utc=batch["captured_utc"],as_of=as_of)
        backup.extend(components)
        source_states.update({"PRIVATE_"+k:v for k,v in report["states"].items()})
    def index(rows):
        out={};ids=set()
        for c in rows:
            k=identity(c["league"],c["home"],c["away"],c["kickoff_utc"])
            if k in out or c["event_id"] in ids:raise ValueError("ambiguous source roster")
            ids.add(c["event_id"]);out[k]=c
        return out
    a,b=index(primary),index(backup)
    pair_dates=defaultdict(set)
    for k in set(a)|set(b):pair_dates[k[:3]].add(k[3])
    selected=[];states=Counter()
    for k in sorted(set(a)|set(b)):
        p,q=a.get(k),b.get(k)
        if now<stamp(REGISTRATION_NOT_BEFORE):
            state="BEFORE_REGISTRATION_WINDOW"
        elif len(pair_dates[k[:3]])!=1:
            state="POSSIBLE_SCHEDULE_CONFLICT"
        elif p is not None and q is not None:
            skew=abs(stamp(p["oldest_market_update_utc"])-stamp(q["oldest_market_update_utc"]))
            delta=max(abs(x-y) for x,y in zip(p["market"]["p"],q["market"]["p"]))
            if skew>MAX_UPDATE_SKEW:
                state="CROSS_SOURCE_UPDATE_SKEW"
            elif delta>MAX_PROB_DELTA:
                state="CROSS_SOURCE_PROBABILITY_CONFLICT"
            else:
                state="PRIMARY_WITH_BACKUP_CONSISTENCY"
        else:
            state="PRIMARY_ONLY" if p is not None else "PRIVATE_BACKUP_ONLY"
        states[state]+=1
        if state in ("PRIMARY_ONLY","PRIMARY_WITH_BACKUP_CONSISTENCY","PRIVATE_BACKUP_ONLY"):
            chosen=p if p is not None else q
            selected.append({"route":state,"component":chosen,"private_only":True,
                             "upstream_independence_proven":False})
    return selected,{"schema":"private-unified-market-routing-v44","status":"HOLD",
            "primary_components":len(a),"private_backup_components":len(b),
            "source_states":dict(source_states),"route_states":dict(states),
            "private_routes":len(selected),"max_probability_delta":MAX_PROB_DELTA,
            "max_update_skew_seconds":int(MAX_UPDATE_SKEW.total_seconds()),
            "provider_calls_made":0,"source_authenticity_verified":False,
            "upstream_independence_proven":False,"public_output_allowed":False,
            "automatic_primary_replacement":False,"market_prices_executable":False,
            "authenticated_samples":0,"training_admission":False,
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
