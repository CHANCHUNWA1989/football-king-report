"""Private, in-memory PropLine 1X2 research adapter; never publish a dataset.

Only caller-supplied response bytes are used. No network, file output, key
access, workflow integration, or authority to redistribute provider data.
"""
from collections import Counter
from datetime import timedelta
import math
from statistics import median
from .research_live_intake_v4 import decode
from .research_candidate_gap_v6 import stamp
from .research_missing_fixture_discovery_v16 import identity
from .research_prospective_fusion_v38 import sha,token

SPORTS={"epl":"soccer_epl","championship":"soccer_efl_champ",
        "bundesliga":"soccer_germany_bundesliga","laliga":"soccer_spain_la_liga",
        "seriea":"soccer_italy_serie_a","ligue1":"soccer_france_ligue_one"}
BOOKS={"pinnacle","bovada","fanduel","draftkings"}
MAX_AGE=timedelta(minutes=20)
MIN_LEAD=timedelta(minutes=15)

def book_vector(book,home,away,now):
    markets=book.get("markets")
    if not isinstance(markets,list) or len(markets)>35:return None
    mains=[m for m in markets if isinstance(m,dict) and m.get("key")=="h2h"
           and m.get("period") in (None,"full","full_game","ft")]
    if len(mains)!=1:return None
    m=mains[0]
    if m.get("suspended_at") is not None:return None
    try:t=stamp(m["last_update"])
    except (KeyError,ValueError,TypeError,OverflowError):return None
    if not timedelta(0)<=now-t<=MAX_AGE:return None
    outcomes=m.get("outcomes")
    if not isinstance(outcomes,list) or len(outcomes)!=3:return None
    prices={}
    for o in outcomes:
        if not isinstance(o,dict) or o.get("point") is not None:return None
        name=o.get("name")
        by_name="home" if name==home else "away" if name==away else "draw" if name=="Draw" else None
        side=o.get("side")
        if side is not None and side!=by_name:return None
        if by_name is None or by_name in prices:return None
        p=o.get("price_decimal")
        if type(p) not in (int,float) or not math.isfinite(p) or not 1.01<=p<=100:return None
        prices[by_name]=1/p
    v=[prices[k] for k in ("home","draw","away")]
    total=sum(v)
    if not .98<=total<=1.35:return None
    return [p/total for p in v],t

def private_components(raw,*,league,captured_utc,as_of):
    """Return private components and a count-only report.

    The input is a locally retained JSON envelope {"events":[...]} containing
    provider rows. Its hash binds the exact envelope, not an authenticated
    vendor response. Never pass components to public signer V40 or Git.
    """
    if league not in SPORTS:raise ValueError("unsupported league")
    now=stamp(as_of);captured=stamp(captured_utc)
    if not timedelta(0)<=now-captured<=MAX_AGE:raise ValueError("stale or future capture")
    d=decode(raw)
    if set(d)!={"events"} or not isinstance(d["events"],list) or len(d["events"])>160:
        raise ValueError("invalid private envelope")
    candidates=[];states=Counter();ids=Counter();fixtures=Counter()
    for r in d["events"]:
        try:
            if not isinstance(r,dict) or r.get("sport_key")!=SPORTS[league]:
                raise ValueError("sport")
            eid=r["id"]
            if type(eid) not in (int,str):raise ValueError("id")
            eid=token(str(eid))
            h,a=r["home_team"],r["away_team"]
            if any(not isinstance(x,str) or not x.strip() or len(x)>100 for x in (h,a)):
                raise ValueError("team")
            k=identity(league,h,a,r["commence_time"])
            ids[eid]+=1;fixtures[k]+=1
            candidates.append((r,eid,k))
        except (KeyError,ValueError,TypeError,OverflowError):
            states["INVALID_IDENTITY"]+=1
    components=[]
    for r,eid,k in candidates:
        if ids[eid]!=1 or fixtures[k]!=1:
            states["DUPLICATE_IDENTITY"]+=1;continue
        if r.get("completed") is True or r.get("is_outright") is True or not now+MIN_LEAD<=k[3]<=now+timedelta(days=14):
            states["NOT_ELIGIBLE_PREMATCH"]+=1;continue
        books=r.get("bookmakers")
        if not isinstance(books,list) or len(books)>70:
            states["INVALID_BOOK_ROSTER"]+=1;continue
        counts=Counter(b.get("key") for b in books if isinstance(b,dict) and isinstance(b.get("key"),str))
        values=[]
        for b in books:
            if not isinstance(b,dict) or not isinstance(b.get("key"),str):continue
            name=b["key"]
            if name not in BOOKS or counts[name]!=1:continue
            v=book_vector(b,r["home_team"],r["away_team"],captured)
            if v is not None and now-v[1]<=MAX_AGE:values.append(v)
        if len(values)<2:
            states["INSUFFICIENT_FRESH_BOOKS"]+=1;continue
        p=[median(v[0][i] for v in values) for i in range(3)]
        total=sum(p)
        components.append({"event_id":eid,"league":league,"home":r["home_team"],"away":r["away_team"],
             "kickoff_utc":k[3].isoformat(),"snapshot_captured_utc":captured.isoformat(),
             "oldest_market_update_utc":min(v[1] for v in values).isoformat(),
             "market":{"p":[v/total for v in p],"captured_utc":min(v[1] for v in values).isoformat(),
                       "source_id":"propline:v1","evidence_sha256":sha(raw)}})
        states["PRIVATE_RESEARCH_COMPONENT"]+=1
    report={"schema":"private-propline-consensus-v43","status":"HOLD",
            "input_events":len(d["events"]),"states":dict(states),
            "private_component_count":len(components),"source_authenticity_verified":False,
            "publication_allowed":False,"provider_calls_made":0,"authenticated_samples":0,
            "production_recommendations":"DISABLED","model_promotion_allowed":False}
    return components,report
