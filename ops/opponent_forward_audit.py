"""Compare previously captured opponent-adjusted and original forecasts on exact later FT observations.

Research only. Archive content is not authenticated by this reader; never backfill
a missing candidate, award qualification credit, or substitute a market price.
"""
import argparse
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path

try:
    from . import opponent_forward_capture as capture
    from .unified_dc_forward_audit import fixture,parse,verify,PROVIDERS,MAX_BYTES,MAX_ARCHIVES,MAX_SCAN_DECODED_BYTES
    from .opponent_adjusted_research import metrics
except ImportError:
    import opponent_forward_capture as capture
    from unified_dc_forward_audit import fixture,parse,verify,PROVIDERS,MAX_BYTES,MAX_ARCHIVES,MAX_SCAN_DECODED_BYTES
    from opponent_adjusted_research import metrics


# A verified pinned cohort may span 21 days of fixtures. Preserve its
# earlier post-match observations across the full cohort without new calls.
DEFAULT_HISTORY_LIMIT=70
DEFAULT_HISTORY_DAYS=14
PINNED_HISTORY_LIMIT=120
PINNED_HISTORY_DAYS=35
SOURCE_HISTORY_DECODED_LIMIT=16_000_000


def history_limits(extended):
    return ((PINNED_HISTORY_LIMIT,PINNED_HISTORY_DAYS) if extended
            else (DEFAULT_HISTORY_LIMIT,DEFAULT_HISTORY_DAYS))


def candidates(doc):
    try:
        if doc.get("schema")!="football-king-uncalibrated-shadow-1" or doc.get("status")!="SHADOW_ONLY":
            return []
        original=dict(doc)
        record=original.pop(capture.TOP_KEY)
        capture.attach(original,record)
        return record["predictions"]
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
        return []


def german_final_votes(report,now):
    """Use existing community German snapshot only with a recorded post-match start.

    This is publisher corroboration, not independently authenticated evidence.
    The older snapshots without a collection start are deliberately excluded.
    """
    votes=defaultdict(set)
    try:
        if (not isinstance(report,dict)
            or report.get("schema")!="football-king-openligadb-hourly-v1"
            or report.get("source")!="OpenLigaDB"
            or report.get("source_type")!="COMMUNITY_CONTRIBUTED_NOT_OFFICIAL_LIVE"
            or report.get("status")!="RESEARCH_ONLY"
            or report.get("production_recommendations")!="DISABLED"
            or report.get("six_league_results_independently_verified") is not False
            or report.get("replaces_bookmaker_market") is not False
            or report.get("used_to_refit_model") is not False):
            return {}
        started=capture.utc(report["started_utc"])
        collected=capture.utc(report["collected_utc"])
        rows=report["matches"]
        if (not timedelta(0)<=collected-started<=timedelta(minutes=5)
            or not timedelta(0)<=now-collected<=timedelta(hours=48)
            or not isinstance(rows,list) or len(rows)>70):
            return {}
        ids=defaultdict(set)
        for r in rows:
            if not isinstance(r,dict) or r.get("league")!="bundesliga" or r.get("status")!="FINISHED_CONFIRMED_BY_SOURCE":
                continue
            try:
                native=r["provider_match_id"]
                k=fixture("bundesliga",r["home"],r["away"],r["kickoff_utc"])
                score=r["score_ft"]
                if (type(native) is not int or native<=0 or started<k[3]+timedelta(hours=2)
                    or not isinstance(score,list) or len(score)!=2
                    or not all(type(v) is int and 0<=v<=30 for v in score)):
                    continue
                ids[native].add(k)
                votes[k].add((native,tuple(score)))
            except (KeyError,ValueError,TypeError,OverflowError):
                continue
        conflicts={k for ks in ids.values() if len(ks)>1 for k in ks}
        return {k:{score for _,score in pairs} for k,pairs in votes.items()
                if k not in conflicts and len({native for native,_ in pairs})==1}
    except (KeyError,ValueError,TypeError,OverflowError):
        return {}


def archived_result_snapshots(root,*,extended=False):
    """Bounded read of existing sanitized source archives, not new API calls."""
    docs=[]
    decoded=0
    limit,_=history_limits(extended)
    if not root or not Path(root).is_dir():
        return docs
    for path in sorted(Path(root).glob("20??/??/??/*.json.gz"),reverse=True)[:limit]:
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size>150_000:
                continue
            with gzip.open(path,"rb") as f:
                raw=f.read(500_001)
            decoded+=len(raw)
            if decoded>SOURCE_HISTORY_DECODED_LIMIT:
                break
            if len(raw)<=500_000:
                docs.append(parse(raw))
        except (OSError,EOFError,ValueError,RecursionError):
            continue
    return docs


def audit(documents,sources,now,german=None,source_history=(),*,extended_history=False):
    out={"schema":"football-king-opponent-forward-audit-v1","status":"HOLD",
         "as_of_utc":now.isoformat(),"production_recommendations":"DISABLED",
         "authenticated_forward_samples":0,"independent_oos_verified":False,
         "positive_ev_verified":False,"recommendation_count":0,
         "archive_authentication_verified":False,"result_authentication_verified":False,
         "archive_documents_scanned":len(documents),"candidate_observations":0,
         "two_publisher_exact_score_count":0,"rows":[],"metrics":None,
         "confidence_interval":None,"reason":"NO_EXACT_SCORE_CANDIDATES","rejected":{}}
    found=defaultdict(list); bindings=defaultdict(set); rejected=Counter()
    for doc in documents:
        for r in candidates(doc):
            try:
                k=fixture(r["league"],r["home"],r["away"],r["kickoff_utc"])
                bindings[(r["league"],r["event_id"])].add(k)
                found[k].append(r)
                out["candidate_observations"]+=1
            except (KeyError,ValueError,TypeError,OverflowError):
                rejected["INVALID_FIXTURE"]+=1
    try:
        stamp=verify(sources,now=now)
        started=capture.utc(sources["started_utc"])
        if not timedelta(0)<=now-stamp<=timedelta(hours=48):
            raise ValueError("STALE_RESULT_SOURCE")
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError):
        out["reason"]="NO_VALID_RESULT_SOURCE"
        return out
    votes=defaultdict(lambda:defaultdict(set))
    native_bindings=defaultdict(set)
    fixture_native_ids=defaultdict(lambda:defaultdict(set))
    valid_history=0
    history_limit,history_days=history_limits(extended_history)
    snapshots=[(sources,timedelta(hours=48))]
    snapshots.extend((d,timedelta(days=history_days)) for d in source_history[:history_limit])
    latest_started=started
    for index,(doc,max_age) in enumerate(snapshots):
        try:
            stamp=verify(doc,now=now)
            opened=capture.utc(doc["started_utc"])
            if not timedelta(0)<=now-stamp<=max_age:
                continue
            if index:
                valid_history+=1
            latest_started=max(latest_started,opened)
            active={p["provider"] for p in doc["providers"]
                    if p.get("configured") is True and p.get("status") in ("PARTIAL","PARTIAL_COVERAGE")}
        except (KeyError,ValueError,TypeError,AttributeError,OverflowError):
            continue
        for r in doc["sampled_fixtures"]:
            if r.get("provider") not in active or r.get("provider") not in PROVIDERS:
                continue
            try:
                k=fixture(r["league"],r["home"],r["away"],r["kickoff_utc"])
                native_bindings[(r["provider"],r["league"],r["provider_event_id"])].add(k)
                fixture_native_ids[k][r["provider"]].add(r["provider_event_id"])
                if r.get("status")!="FINISHED":
                    continue
                score=r["score_ft"]
                if (not isinstance(score,list) or len(score)!=2
                    or not all(type(v) is int and 0<=v<=30 for v in score)
                    or opened<k[3]+timedelta(hours=2)):
                    continue
                votes[k][r["provider"]].add(tuple(score))
            except (KeyError,ValueError,TypeError,OverflowError):
                continue
    out["valid_result_history_snapshots"]=valid_history
    out["result_history_scan_limit"]=history_limit
    out["result_history_max_age_days"]=history_days
    out["result_history_decoded_bytes_limit"]=SOURCE_HISTORY_DECODED_LIMIT
    out["result_history_is_not_complete"]=True
    native_conflicts={k for keys in native_bindings.values() if len(keys)>1 for k in keys}
    # One fixture must bind to at most one native ID per publisher,
    # including across snapshots and scheduled-to-finished transitions.
    # Matching scores alone do not resolve competing native identities.
    duplicate_native_ids={k for k,providers in fixture_native_ids.items()
                          if any(len(ids)>1 for ids in providers.values())}
    german_votes=german_final_votes(german,now)
    for k,scores in german_votes.items():
        votes[k]["openligadb"]=scores
    out["german_community_final_observations"]=len(german_votes)
    ambiguous={k for group in bindings.values() if len(group)>1 for k in group}
    for k,items in sorted(found.items()):
        if k in ambiguous:
            rejected["CROSS_ARCHIVE_EVENT_CONFLICT"]+=1
            continue
        if k in native_conflicts:
            rejected["RESULT_SOURCE_NATIVE_ID_CONFLICT"]+=1
            continue
        if k in duplicate_native_ids:
            rejected["AMBIGUOUS_PROVIDER_FIXTURE_ID"]+=1
            continue
        if latest_started<k[3]+timedelta(hours=2):
            rejected["RESULT_NOT_POST_MATCH"]+=1
            continue
        first=min(capture.utc(r["candidate_prediction_utc"]) for r in items)
        earliest=[r for r in items if capture.utc(r["candidate_prediction_utc"])==first]
        r=earliest[0]
        if any(x!=r for x in earliest):
            rejected["CONFLICTING_EARLIEST_CAPTURE"]+=1
            continue
        publishers=votes.get(k,{})
        if len(publishers)<2:
            rejected["FEWER_THAN_TWO_PUBLISHERS"]+=1
            continue
        scores=set().union(*publishers.values())
        if len(scores)!=1 or any(len(x)!=1 for x in publishers.values()):
            rejected["CONFLICTING_FINAL_SCORES"]+=1
            continue
        gh,ga=next(iter(scores))
        out["rows"].append({"league":k[0],"event_id":r["event_id"],
            "kickoff_utc":k[3].isoformat(),"candidate_prediction_utc":first.isoformat(),
            "score_ft":[gh,ga],"y":0 if gh>ga else 1 if gh==ga else 2,
            "original":r["original"],"candidate":r["p"],"publisher_count":len(publishers),
            "training_sha256":r["training_sha256"],"independently_authenticated":False})
    rows=out["rows"]
    out["two_publisher_exact_score_count"]=len(rows)
    out["rejected"]=dict(rejected)
    if rows:
        out["reason"]="UNAUTHENTICATED_FORWARD_RESEARCH_ONLY"
        out["metrics"]={key:metrics(rows,key) for key in ("original","candidate")}
        out["paired_log_loss_gain"]=out["metrics"]["original"]["log_loss"]-out["metrics"]["candidate"]["log_loss"]
    return out


def verified_artifacts(specs):
    """Verify bounded, explicitly pinned artifacts before cross-run scoring."""
    if len(specs)>4:
        raise ValueError("TOO_MANY_RESEARCH_ARTIFACTS")
    try:
        from .readonly_artifact_verify import verify_artifact
    except ImportError:
        from readonly_artifact_verify import verify_artifact
    docs,reports=[],[]
    seen=set()
    for spec in specs:
        if len(spec)!=4 or tuple(spec[2:]) in seen:
            raise ValueError("DUPLICATE_OR_INVALID_ARTIFACT_IDENTITY")
        seen.add(tuple(spec[2:]))
        doc,report=verify_artifact(*spec)
        docs.append(doc)
        reports.append(report)
    return docs,reports


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archives",required=True);p.add_argument("--sources",required=True)
    p.add_argument("--output",required=True);p.add_argument("--german");p.add_argument("--source-history")
    p.add_argument("--research-artifact");p.add_argument("--artifact-sha256")
    p.add_argument("--artifact-run-id");p.add_argument("--artifact-attempt")
    p.add_argument("--additional-research-artifact",nargs=4,action="append",default=[],
                   metavar=("PATH","SHA256","RUN_ID","ATTEMPT"))
    p.add_argument("--pinned-only",action="store_true",help="Score only verified explicit forecast artifacts; never admit local archive forecasts.")
    a=p.parse_args()
    artifact_args=(a.research_artifact,a.artifact_sha256,a.artifact_run_id,a.artifact_attempt)
    if any(artifact_args) and not all(artifact_args):
        p.error("artifact, expected digest, run id and attempt must be supplied together")
    if a.pinned_only and not (all(artifact_args) or a.additional_research_artifact):
        p.error("--pinned-only requires at least one explicit verified artifact")
    docs=[];decoded=0;invalid=0
    archive_paths=[] if a.pinned_only else sorted(Path(a.archives).glob("**/*.json.gz"),reverse=True)[:MAX_ARCHIVES]
    for path in archive_paths:
        try:
            if path.is_symlink() or path.stat().st_size>MAX_BYTES:
                raise ValueError("INVALID_ARCHIVE")
            with gzip.open(path,"rb") as f:
                raw=f.read(MAX_BYTES+1)
            if decoded+len(raw)>MAX_SCAN_DECODED_BYTES:
                break
            decoded+=len(raw)
            docs.append(parse(raw))
        except (OSError,EOFError,ValueError,RecursionError):
            invalid+=1
    try:
        with Path(a.sources).open("rb") as f:
            sources=parse(f.read(MAX_BYTES+1))
    except (OSError,ValueError,RecursionError):
        sources=None
    german=None
    if a.german:
        try:
            with Path(a.german).open("rb") as f:
                german=parse(f.read(MAX_BYTES+1))
        except (OSError,ValueError,RecursionError):
            pass
    specs=([artifact_args] if a.research_artifact else [])+a.additional_research_artifact
    artifact_docs,artifact_reports=verified_artifacts(specs)
    docs.extend(artifact_docs)
    artifact_report=artifact_reports[0] if a.research_artifact else None
    pinned_keys={fixture(r["league"],r["home"],r["away"],r["kickoff_utc"])
                 for doc in artifact_docs for r in candidates(doc)}
    # Only successfully verified explicit artifact input extends the
    # historical observation window. The latest source still needs freshness.
    extended=bool(artifact_docs)
    result=audit(docs,sources,datetime.now(timezone.utc),german=german,
                 source_history=archived_result_snapshots(a.source_history,extended=extended),
                 extended_history=extended)
    result["readonly_artifact_verification"]=artifact_report
    result["readonly_artifact_verifications"]=artifact_reports
    result["readonly_artifact_unique_fixture_count"]=len(pinned_keys)
    result["forecast_scope"]="PINNED_ARTIFACTS_ONLY" if a.pinned_only else "LOCAL_ARCHIVES_AND_EXPLICIT_ARTIFACTS"
    if a.pinned_only:
        assert result["two_publisher_exact_score_count"]<=len(pinned_keys)
    result.update(invalid_archives=invalid,scan_is_not_complete_history=True,archive_scan_limit=MAX_ARCHIVES)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","reason","candidate_observations","two_publisher_exact_score_count","production_recommendations")}))


if __name__=="__main__":
    main()
