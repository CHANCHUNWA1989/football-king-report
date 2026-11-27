"""Read existing archived fixed DC forecasts and compare on later exact FT observations.

Research only: Git archives and provider status are not independently authenticated.
No backfilling, refitting, quote inputs, or qualification changes.
"""
import argparse
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from . import model_dixon_coles_forward as dc
    from .source_publish_guard import verify
    from .team_identity import team_id
except ImportError:
    import model_dixon_coles_forward as dc
    from source_publish_guard import verify
    from team_identity import team_id

SCHEMA = "football-king-fixed-dc-forward-score-audit-v1"
PROVIDERS = ("thesportsdb","api_football","football_data_org")
MAX_ARCHIVES = 120
MAX_BYTES = 8_000_000


def unique(pairs):
    out = {}
    for k,v in pairs:
        if k in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[k]=v
    return out


def nonfinite(_):
    raise ValueError("NONFINITE_JSON")


def parse(raw):
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError("INVALID_BYTES")
    return json.loads(raw,object_pairs_hook=unique,parse_constant=nonfinite)


def fixture(league,home,away,kickoff):
    h,a=team_id(league,home),team_id(league,away)
    if league not in dc.LEAGUES or not h or not a or h==a:
        raise ValueError("INVALID_FIXTURE")
    return league,h,a,dc._utc(kickoff)


def archive_candidates(doc):
    if (not isinstance(doc,dict) or doc.get("schema")!="football-king-uncalibrated-shadow-1"
        or doc.get("production_recommendations")!="DISABLED" or doc.get("status")!="SHADOW_ONLY"):
        return []
    cap=doc.get(dc.TOP_KEY)
    if (not isinstance(cap,dict) or cap.get("schema")!=dc.SCHEMA
        or cap.get("model_id")!=dc.MODEL or cap.get("protocol_sha256")!=dc.PROTOCOL_SHA256
        or cap.get("protocol")!=dc.PROTOCOL or cap.get("frozen_rho")!=dc.RHO
        or cap.get("parameter_fitting_performed") is not False
        or cap.get("automatic_model_promotion") is not False
        or cap.get("production_recommendations")!="DISABLED"
        or cap.get("status")!="FORWARD_RESEARCH_CAPTURE_ONLY"):
        return []
    try:
        at=dc._utc(cap["generated_utc"])
        if not dc._implementation_matches():
            return []
        # Recompute from the original same-document rates at the recorded
        # candidate clock. Never derive a missing candidate after kickoff.
        expected=dc.build(doc,now=at)
        supplied=cap["predictions"]
        if (not isinstance(supplied,list) or len(supplied)>dc.MAX_ROWS
            or type(cap.get("predictions_count")) is not int
            or cap["predictions_count"]!=len(supplied)
            or cap.get("source_as_of_utc")!=expected.get("source_as_of_utc")
            or expected["predictions"]!=supplied):
            return []
        return supplied
    except (KeyError,ValueError,TypeError,OverflowError,AttributeError):
        return []


def score_probability(h,a,rho,gh,ga):
    # The registered forward protocol has a normalized 0..11 score grid.
    # Scores outside that support remain in 1X2 metrics, not score log loss.
    if gh>11 or ga>11:
        return None
    hp=[math.exp(-h)*h**i/math.factorial(i) for i in range(12)]
    ap=[math.exp(-a)*a**i/math.factorial(i) for i in range(12)]
    tau={(0,0):1-h*a*rho,(0,1):1+h*rho,(1,0):1+a*rho,(1,1):1-rho}
    z=math.fsum(x*y*tau.get((i,j),1) for i,x in enumerate(hp) for j,y in enumerate(ap))
    return hp[gh]*ap[ga]*tau.get((gh,ga),1)/z


def metrics(rows):
    if not rows:
        return None
    out={}
    for name in ("derived_rho0","candidate"):
        p=[(row[name],row["outcome"]) for row in rows]
        out[name]={"n":len(p),"brier":math.fsum(sum((v-(i==y))**2 for i,v in enumerate(vec)) for vec,y in p)/len(p),
                   "log_loss":math.fsum(-math.log(max(vec[y],1e-15)) for vec,y in p)/len(p)}
        scores=[r[name+"_score_probability"] for r in rows if r[name+"_score_probability"] is not None]
        out[name]["score_log_loss_n"]=len(scores)
        out[name]["score_log_loss"]=math.fsum(-math.log(max(v,1e-15)) for v in scores)/len(scores) if scores else None
    return out


def audit(documents,sources,now):
    now=dc._clock(now)
    out={"schema":SCHEMA,"as_of_utc":now.isoformat(),"status":"HOLD",
         "production_recommendations":"DISABLED","recommendation_count":0,
         "parameter_refitting_performed":False,"independent_oos_verified":False,
         "authenticated_forward_samples":0,"profitability_verified":False,
         "archive_authentication_verified":False,"result_authentication_verified":False,
         "archive_documents_scanned":len(documents),"archived_candidate_observations":0,
         "two_publisher_exact_score_candidate_count":0,"rejected":{},"metrics":None,
         "rows":[]}
    found=defaultdict(list)
    rejects=Counter()
    for doc in documents:
        for row in archive_candidates(doc):
            try:
                k=fixture(row["league"],row["home"],row["away"],row["kickoff_utc_recorded"])
                found[k].append(row)
                out["archived_candidate_observations"]+=1
            except (ValueError,TypeError,KeyError):
                rejects["INVALID_CANDIDATE_IDENTITY"]+=1
    try:
        stamp=verify(sources,now=now)
        started=dc._utc(sources["started_utc"])
        if not timedelta(0)<=now-stamp<=timedelta(hours=48):
            raise ValueError("STALE_OR_FUTURE_RESULT_AUDIT")
    except (ValueError,KeyError,TypeError,OverflowError,AttributeError):
        out["reason"]="NO_VALID_RESULT_SOURCE_SNAPSHOT"
        out["rejected"]=dict(rejects)
        return out
    votes=defaultdict(lambda:defaultdict(set))
    for row in sources["sampled_fixtures"]:
        if row.get("provider") not in PROVIDERS or row.get("status")!="FINISHED":
            continue
        try:
            k=fixture(row["league"],row["home"],row["away"],row["kickoff_utc"])
            score=row["score_ft"]
            if (not isinstance(score,list) or len(score)!=2
                or not all(type(v) is int and 0<=v<=30 for v in score)
                or started<k[3]+timedelta(hours=2)):
                continue
            votes[k][row["provider"]].add(tuple(score))
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
    for k,items in found.items():
        if not k[3]+timedelta(hours=2)<=started:
            rejects["NOT_POST_MATCH_OBSERVATION"]+=1
            continue
        # Earliest captured candidate in the bounded scan. Conflicting copies
        # at that time are quarantined, never selected by observed outcome.
        first=min(dc._utc(r["prediction_utc"]) for r in items)
        earliest=[r for r in items if dc._utc(r["prediction_utc"])==first]
        if any(r!=earliest[0] for r in earliest):
            rejects["CONFLICTING_EARLIEST_CAPTURE"]+=1
            continue
        row=earliest[0]
        publisher=votes.get(k,{})
        if len(publisher)<2:
            rejects["FEWER_THAN_TWO_PUBLISHERS"]+=1
            continue
        if any(len(v)!=1 for v in publisher.values()) or len(set.union(*(set(v) for v in publisher.values())))!=1:
            rejects["CONFLICTING_FINAL_SCORES"]+=1
            continue
        gh,ga=next(iter(next(iter(publisher.values()))))
        y=0 if gh>ga else 1 if gh==ga else 2
        result={"league":k[0],"event_id":row["event_id"],"kickoff_utc":k[3].isoformat(),
                "prediction_utc":first.isoformat(),"score_ft":[gh,ga],"outcome":y,
                "publisher_count":len(publisher),"source_projection_sha256":row["source_projection_sha256"],
                "derived_rho0":row["derived_rho0"],"candidate":row["candidate"],
                "derived_rho0_score_probability":score_probability(row["expected_home_goals"],row["expected_away_goals"],0.,gh,ga),
                "candidate_score_probability":score_probability(row["expected_home_goals"],row["expected_away_goals"],dc.RHO,gh,ga),
                "independently_authenticated":False}
        out["rows"].append(result)
    out["rejected"]=dict(rejects)
    out["two_publisher_exact_score_candidate_count"]=len(out["rows"])
    out["metrics"]=metrics(out["rows"])
    out["reason"]="UNAUTHENTICATED_FORWARD_RESEARCH_ONLY" if out["rows"] else "NO_EXACT_SCORE_CANDIDATES"
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archives",required=True)
    p.add_argument("--sources",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    docs=[]
    invalid=0
    # Bounded scan of most recent archive filenames; never rewrite old bytes.
    files=sorted(Path(args.archives).glob("**/*.json.gz"),reverse=True)[:MAX_ARCHIVES]
    for path in files:
        try:
            if path.is_symlink() or path.stat().st_size>MAX_BYTES:
                raise ValueError("INVALID_ARCHIVE")
            with gzip.open(path,"rb") as stream:
                docs.append(parse(stream.read(MAX_BYTES+1)))
        except (OSError,EOFError,ValueError,RecursionError):
            invalid+=1
    try:
        with Path(args.sources).open("rb") as stream:
            source=parse(stream.read(MAX_BYTES+1))
    except (OSError,ValueError,RecursionError):
        source=None
    result=audit(docs,source,datetime.now(timezone.utc))
    result["invalid_archives"]=invalid
    result["archive_scan_limit"]=MAX_ARCHIVES
    result["scan_is_not_complete_history"]=True
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(result,allow_nan=False,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)
    print(json.dumps({"status":result["status"],"reason":result["reason"],
        "research_score_candidates":result["two_publisher_exact_score_candidate_count"]}))


if __name__=="__main__":
    main()
