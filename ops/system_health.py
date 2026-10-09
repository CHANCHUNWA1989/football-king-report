"""Explainable zero-API-credit operational health of Football King.

Reads already archived metadata. Detects missing sources, stale snapshots,
forward evidence gaps and unresolved pre-match cases without looking up any
external provider. Never creates new model evidence or enables wagers.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from forward_validation import load_archived, valid_prior_sample
from market_pair import iso

LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
SCHEMA = "football-king-observability-v1"


def _age(document, field, now, max_hours):
    try:
        age = (now - iso(document[field])).total_seconds() / 3600
        if not -5/60 <= age <= max_hours:
            return "STALE_OR_FUTURE", round(age,2)
        return "CURRENT", round(age,2)
    except (KeyError, ValueError, TypeError, OverflowError):
        return "INVALID_CLOCK", None


def analyze(*, evidence, market, secondary, wide, extensions, archived, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    documents = (evidence, market, secondary, wide, extensions)
    if any(not isinstance(x, dict) for x in documents):
        raise ValueError("UNSAFE_MONITOR_DOCUMENT")
    if any(x.get("production_recommendations") != "DISABLED" for x in documents):
        raise ValueError("UNSAFE_MONITOR_SOURCE")
    rows = evidence.get("samples")
    if (not isinstance(rows, list) or type(evidence.get("n")) is not int
            or evidence["n"] != len(rows) or len(rows) > 20000):
        raise ValueError("BROKEN_SETTLEMENT_COUNT")
    if any(not valid_prior_sample(x) for x in rows):
        raise ValueError("INVALID_PRIOR_EVIDENCE")
    if not isinstance(archived,list) or len(archived)>20000:
        raise ValueError("INVALID_ARCHIVED_COLLECTION")
    settled = {r["key"] for r in rows}
    upcoming, finished_unsettled, unique = 0, 0, set()
    by_league = Counter()
    for key, data in archived:
        if (not isinstance(key, tuple) or len(key)!=4
                or not isinstance(data, dict)):
            raise ValueError("INVALID_ARCHIVED_FORECAST")
        encoded = json.dumps(key,ensure_ascii=False)
        if encoded in unique:
            raise ValueError("DUPLICATE_ARCHIVED_CASE")
        unique.add(encoded)
        if encoded in settled:
            continue
        kick = iso(data["kickoff_utc"])
        by_league[data["league"]]+=1
        if now < kick:
            upcoming+=1
        else:
            finished_unsettled+=1

    source_snapshots = {}
    for name, doc, field, max_hours in (
        ("free_fixtures", secondary, "collected_utc", 36),
        ("wide_leagues", wide, "collected_utc", 72),
        ("historic_catalog", extensions, "completed_utc", 168),
        ("market", market, "as_of_utc", 26),
    ):
        status, age = _age(doc,field,now,max_hours)
        source_snapshots[name]={"status":status,"age_hours":age,
                                "allowed_age_hours":max_hours}
    providers = []
    for group, doc in (("secondary",secondary),("wide",wide),
                       ("historical",extensions)):
        for item in doc.get("providers",[]):
            if not isinstance(item,dict) or not isinstance(item.get("provider"),str):
                raise ValueError("INVALID_PROVIDER_METADATA")
            providers.append({"group":group,"provider":item["provider"],
                              "status":item.get("status","UNKNOWN"),
                              "configured":item.get("configured") is True})
    market_rows = market.get("events", [])
    if not isinstance(market_rows,list):
        raise ValueError("INVALID_MARKET_EVENTS")
    market_leagues=Counter(x.get("league") for x in market_rows if isinstance(x,dict))
    secondary_leagues=Counter()
    for x in secondary.get("sampled_fixtures",[]):
        if isinstance(x,dict) and x.get("league") in LEAGUES:
            secondary_leagues[x["league"]]+=1
    per_league = {code:{"market_observations":market_leagues[code],
                        "free_fixture_samples":secondary_leagues[code],
                        "archived_unsettled_forecasts":by_league[code]}
                  for code in LEAGUES}
    reasons=[]
    if evidence["n"] == 0:
        reasons.append("NO_SETTLED_OUT_OF_SAMPLE_CASES")
    if evidence["n"] < 300:
        reasons.append("LESS_THAN_300_VALID_FORWARD_SAMPLES")
    if finished_unsettled:
        reasons.append("FINISHED_KICKOFF_ARCHIVES_AWAIT_SCORE_SETTLEMENT")
    if any(x["status"] != "CURRENT" for x in source_snapshots.values()):
        reasons.append("ONE_OR_MORE_STALE_OR_UNKNOWN_SOURCE_SNAPSHOTS")
    if any(p["status"] in ("HOLD","NOT_CONFIGURED") for p in providers):
        reasons.append("OPTIONAL_FREE_PROVIDERS_MISSING_COVERAGE")
    if any(not per_league[lg]["market_observations"] for lg in LEAGUES):
        reasons.append("AT_LEAST_ONE_LEAGUE_MISSING_1X2_MARKET")
    quota=market.get("quota")
    quota_remaining=(quota.get("remaining") if isinstance(quota,dict)
                     and type(quota.get("remaining")) is int else None)
    if quota_remaining is None or quota_remaining <= 140:
        reasons.append("MARKET_FREE_CREDIT_RESERVE_UNKNOWN_OR_LOW")
    return {
        "schema":SCHEMA,"generated_utc":now.isoformat(),
        "status":"RESEARCH_ONLY" if not reasons else "HOLD",
        "evidence_status":"INSUFFICIENT_FORWARD_VALIDATION" if evidence["n"]<300
                          else "INDEPENDENT_REVIEW_REQUIRED",
        "settled_forward_cases":evidence["n"],
        "forward_sample_target_for_review":300,
        "archived_unique_prematch_cases":len(archived),
        "archived_waiting_kickoff":upcoming,
        "archived_past_kickoff_not_settled":finished_unsettled,
        "source_snapshot_health":source_snapshots,
        "free_provider_status":providers,
        "market_free_quota_remaining":quota_remaining,
        "per_league":per_league,
        "attention_reasons":reasons,
        "zero_extra_api_calls":True,
        "source_event_times_used_for_training":False,
        "model_probabilities_rewritten":False,
        "results_independently_verified":False,
        "market_bookmaker_quotes_are_executable":False,
        "production_recommendations":"DISABLED",
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence",default="evidence/settled.json")
    parser.add_argument("--market",default="market/latest.json")
    parser.add_argument("--secondary",default="sources/latest.json")
    parser.add_argument("--wide",default="sources/wide_latest.json")
    parser.add_argument("--extensions",default="sources/research_extensions_latest.json")
    parser.add_argument("--archive",default="research_pairs")
    parser.add_argument("--output",default="ops-health.json")
    args=parser.parse_args(argv)
    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    result=analyze(evidence=load(args.evidence),
                   market=load(args.market),secondary=load(args.secondary),
                   wide=load(args.wide),extensions=load(args.extensions),
                   archived=load_archived(args.archive))
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                                 encoding="utf-8")
    print(json.dumps({"status":result["status"],
                      "settled_forward_cases":result["settled_forward_cases"],
                      "archived_waiting_kickoff":result["archived_waiting_kickoff"],
                      "archived_past_kickoff_not_settled":result["archived_past_kickoff_not_settled"],
                      "attention_reasons":result["attention_reasons"],
                      "production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
