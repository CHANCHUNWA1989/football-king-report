"""Capture the exact research-selection bytes observed during a GitHub run.

A run artifact is useful forward evidence of what the pipeline *displayed*,
not proof of authentic ChatGPT message time, upstream forecast creation time,
bookmaker executable odds, a particular fixture outcome, or future skill.
The existing signed forecast provenance process is separate.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re

SCHEMA="football-king-run-observed-research-decisions-v1"
SOURCE_SCHEMA="football-king-explainable-research-selections-v1"
GROUPS=("selections","reviews","model_only_watchlist")
MAX_INPUT_BYTES=2_000_000


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _utc(value):
    _require(isinstance(value,str), "INVALID_UTC_TIME")
    try:
        date=datetime.fromisoformat(value.replace("Z","+00:00"))
    except (ValueError, OverflowError):
        raise ValueError("INVALID_UTC_TIME") from None
    _require(date.tzinfo is not None, "NAIVE_UTC_TIME")
    return date.astimezone(timezone.utc)


def _pairs(items):
    out={}
    for k,v in items:
        _require(k not in out, "DUPLICATE_JSON_KEY")
        out[k]=v
    return out


def build(source_bytes, *, run_id, attempt, sha, now=None):
    _require(type(source_bytes) is bytes and 0<len(source_bytes)<=MAX_INPUT_BYTES,
             "INVALID_RESEARCH_SOURCE_BYTES")
    _require(isinstance(run_id,str) and re.fullmatch(r"[1-9][0-9]{0,19}",run_id)
             and isinstance(attempt,str) and re.fullmatch(r"[1-9][0-9]{0,9}",attempt)
             and isinstance(sha,str) and re.fullmatch(r"[0-9a-f]{40}",sha),
             "INVALID_GITHUB_RUN_CONTEXT")
    now=datetime.now(timezone.utc) if now is None else now
    _require(isinstance(now,datetime) and now.tzinfo is not None,
             "INVALID_CAPTURE_CLOCK")
    now=now.astimezone(timezone.utc)
    try:
        source=json.loads(source_bytes,object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("NONFINITE_JSON_NUMBER")))
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("INVALID_RESEARCH_SOURCE_JSON") from None
    _require(isinstance(source,dict) and source.get("schema")==SOURCE_SCHEMA
             and source.get("production_recommendations")=="DISABLED"
             and source.get("status") in ("HOLD","RESEARCH_ONLY")
             and source.get("automatic_bets") is False
             and source.get("value_recommendation_count")==0,
             "UNSAFE_RESEARCH_SOURCE")
    source_asof=_utc(source.get("as_of_utc"))
    _require(source_asof<=now, "RESEARCH_SOURCE_TIMESTAMP_IN_FUTURE")
    all_ids=set()
    decisions=[]
    counts={}
    eligible=0
    for group, count_key in zip(GROUPS,("selected_count","review_count","model_only_count")):
        rows=source.get(group)
        _require(type(rows) is list and len(rows)<=100
                 and type(source.get(count_key)) is int
                 and source[count_key]==len(rows), "INVALID_RESEARCH_GROUP_COUNT")
        counts[group]=len(rows)
        for row in rows:
            _require(isinstance(row,dict), "INVALID_RESEARCH_CANDIDATE")
            key=row.get("event_id") if group=="model_only_watchlist" else row.get("case_id")
            _require(type(key) is str and 1<=len(key)<=300 and key not in all_ids,
                     "DUPLICATE_OR_MISSING_RESEARCH_ID")
            all_ids.add(key)
            _require(row.get("direction") in ("HOME","DRAW","AWAY")
                     and row.get("production_recommendations")=="DISABLED"
                     and row.get("qualifies_for_betting") is not True
                     and row.get("value_bet_verified") is False
                     and row.get("executable_market_odds_available") is False,
                     "UNSAFE_RESEARCH_CANDIDATE")
            kickoff=_utc(row.get("kickoff_utc"))
            predicted=_utc(row.get("prediction_utc"))
            _require(predicted<=now and predicted<kickoff,
                     "FORECAST_TIME_NOT_BEFORE_CAPTURE_AND_KICKOFF")
            current=kickoff>now+timedelta(minutes=60)
            eligible+=int(current)
            decisions.append({
                "group":group,"source_case_or_event_id":key,
                "direction":row["direction"],
                "kickoff_utc":kickoff.isoformat(),
                "source_claimed_prediction_utc":predicted.isoformat(),
                "eligible_at_observation":current,
                "source_claimed_prediction_time_independently_authenticated":False,
            })
    return {
        "schema":SCHEMA,"status":"HOLD" if not eligible else "RESEARCH_ONLY",
        "source_status":source["status"],
        "run_id":run_id,"run_attempt":attempt,"workflow_source_commit_sha":sha,
        "observed_utc_runner_clock":now.isoformat(),
        "source_as_of_utc":source_asof.isoformat(),
        "research_selections_sha256":hashlib.sha256(source_bytes).hexdigest(),
        "observed_count":len(decisions),
        "observed_group_counts":counts,
        "eligible_at_observation_count":eligible,
        "observations":decisions,
        "source_generated_at_observation":False,
        "chat_message_timestamps_authenticated":False,
        "independent_publication_timestamp_verified":False,
        "original_model_forecast_seal_authenticated_by_this_artifact":False,
        "future_model_skill_proven":False,
        "executable_odds_authenticated":False,
        "can_enter_formal_settlement_ledger":False,
        "certified_forward_samples":0,
        "roi":None,"ev":None,
        "production_recommendations":"DISABLED",
        "notice_zh":"GitHub當次執行見到的原始研究選向；採集時間只為Runner時鐘，需GitHub外部記錄核實。不是ChatGPT對話封存、模型原始產生時刻、正式正EV或可成交報價。",
    }


def publish(source, destination, *, run_id, attempt, sha, now=None):
    source,destination=Path(source),Path(destination)
    _require(source.resolve()!=destination.resolve()
             and destination.resolve()!=source.resolve().parent, "UNSAFE_CAPTURE_DESTINATION")
    _require(source.is_file() and not source.is_symlink(), "MISSING_OR_UNSAFE_RESEARCH_SOURCE")
    with source.open("rb") as stream:
        raw=stream.read(MAX_INPUT_BYTES+1)
    report=build(raw,run_id=run_id,attempt=attempt,sha=sha,now=now)
    _require(not destination.exists() and not destination.is_symlink(),
             "RESEARCH_OBSERVATION_ALREADY_EXISTS")
    try:
        destination.mkdir(parents=True,exist_ok=False)
    except FileExistsError:
        raise ValueError("RESEARCH_OBSERVATION_ALREADY_EXISTS") from None
    (destination/"research_selections.json").write_bytes(raw)
    (destination/"observation.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
        encoding="utf-8")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--output-dir",required=True)
    args=p.parse_args()
    result=publish(args.source,args.output_dir,
                   run_id=os.environ.get("GITHUB_RUN_ID",""),
                   attempt=os.environ.get("GITHUB_RUN_ATTEMPT",""),
                   sha=os.environ.get("GITHUB_SHA",""))
    print(json.dumps({"status":result["status"],
                      "observed_count":result["observed_count"],
                      "eligible_at_observation_count":result["eligible_at_observation_count"],
                      "production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
