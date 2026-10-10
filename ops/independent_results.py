"""Audit independent FREE 90-minute final-score agreement without rewriting evidence.

Only observations in a verified source snapshot may corroborate a previously
sealed forward sample. No new predictions or releases are created here.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone, date
from pathlib import Path
from source_publish_guard import verify
from team_identity import team_id

PROVIDERS=("thesportsdb","api_football","football_data_org")
LEAGUES=("epl","championship","bundesliga","laliga","seriea","ligue1")


def utc(text):
    t=datetime.fromisoformat(str(text).replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_UTC")
    return t.astimezone(timezone.utc)


def bundesliga_candidate_audit(evidence, crosscheck, now):
    """Correlate two published FT score observations to sealed outcomes.

    This never changes evidence, creates a settled sample, or upgrades
    independently_verified flags; publishing agreement is not an attestation.
    """
    result = {
        "status": "HOLD", "two_publisher_ft_candidate_fixtures": 0,
        "settled_outcomes_correlated": 0, "settled_outcome_conflicts": 0,
        "ambiguous_correlations": 0,
        "results_cryptographically_attested": False,
        "forward_predictions_independently_validated": False,
    }
    if not isinstance(crosscheck, dict):
        return result
    try:
        if (crosscheck.get("schema") !=
                "football-king-bundesliga-two-publisher-score-candidates-v1"
                or crosscheck.get("status") != "PARTIAL_CHECK"
                or crosscheck.get("production_recommendations") != "DISABLED"
                or crosscheck.get("sources") != ["OpenLigaDB", "OpenFootball"]
                or crosscheck.get("score_conflicts") != 0
                or crosscheck.get("errors") != []
                or crosscheck.get("all_leagues_verified") is not False
                or crosscheck.get("independent_kickoff_verification") is not False):
            return result
        captured = utc(crosscheck["as_of_utc"])
        if not -300 <= (now-captured).total_seconds() <= 6*3600:
            return result
        cases = crosscheck["two_publisher_matching_ft_candidates"]
        if (not isinstance(cases, list) or len(cases) > 400
                or type(crosscheck.get("two_publisher_matching_ft_candidate_count")) is not int
                or crosscheck["two_publisher_matching_ft_candidate_count"] != len(cases)
                or type(crosscheck.get("score_comparisons")) is not int
                or crosscheck["score_comparisons"] < len(cases)):
            return result
        index = {}
        for row in cases:
            if not isinstance(row, dict) or row.get("league") != "bundesliga":
                return result
            home = team_id("bundesliga", row.get("home"))
            away = team_id("bundesliga", row.get("away"))
            day1, day2 = date.fromisoformat(row["date_first"]), date.fromisoformat(row["date_second"])
            score = row["score_ft"]
            if (not home or not away or home == away
                    or abs((day1-day2).days) > 1
                    or not isinstance(score, list) or len(score) != 2
                    or not all(type(n) is int and 0 <= n <= 30 for n in score)):
                return result
            key = (home, away, day1, day2)
            if key in index:
                return result
            index[key] = tuple(score)
        result["two_publisher_ft_candidate_fixtures"] = len(index)
        unique = set()
        for sample in evidence.get("samples", []):
            if (not isinstance(sample, dict)
                    or sample.get("league") != "bundesliga"
                    or not isinstance(sample.get("key"), str)
                    or sample["key"] in unique):
                continue
            unique.add(sample["key"])
            key = json.loads(sample["key"])
            if (not isinstance(key, list) or len(key) != 4
                    or key[0] != "bundesliga"
                    or type(sample.get("y")) is not int
                    or sample["y"] not in (0, 1, 2)):
                continue
            ko = utc(sample["kickoff_utc"]).date()
            home, away = team_id("bundesliga", key[1]), team_id("bundesliga", key[2])
            if not home or not away or home == away:
                continue
            matches = [score for (h, a, d1, d2), score in index.items()
                       if h == home and a == away
                       and abs((d1-ko).days) <= 1
                       and abs((d2-ko).days) <= 1]
            if len(matches) > 1:
                result["ambiguous_correlations"] += 1
            elif len(matches) == 1:
                h, a = matches[0]
                outcome = 0 if h > a else 1 if h == a else 2
                if outcome == sample["y"]:
                    result["settled_outcomes_correlated"] += 1
                else:
                    result["settled_outcome_conflicts"] += 1
        result["status"] = "CANDIDATE_CORRELATION_ONLY"
        return result
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError,
            json.JSONDecodeError):
        return {
            "status": "HOLD", "two_publisher_ft_candidate_fixtures": 0,
            "settled_outcomes_correlated": 0, "settled_outcome_conflicts": 0,
            "ambiguous_correlations": 0,
            "results_cryptographically_attested": False,
            "forward_predictions_independently_validated": False,
        }


def compare(evidence, sources, now=None, crosscheck=None):
    now=now or datetime.now(timezone.utc)
    result={"schema":"football-king-independent-final-score-audit-v1",
            "status":"HOLD","settled_evidence_count":0,
            "duplicate_evidence_samples":0,"unique_evidence_keys_count":0,
            "single_source_agreements":0,"two_provider_agreements":0,
            "two_provider_exact_score_agreements":0,
            "same_outcome_different_final_score_conflicts":0,
            "conflicting_observations":0,"unmatched_samples":0,
            "provider_counts":{p:0 for p in PROVIDERS},
            "provenance":"FREE_SOURCE_ARCHIVED_AFTER_OUTCOME_NOT_POINT_IN_TIME_MARKET",
            "all_six_leagues_verified":False,"independently_validated_prediction_value":False,
            "profitability_verified":False,"can_unlock_betting":False,
            "production_recommendations":"DISABLED"}
    if (not isinstance(evidence,dict) or evidence.get("production_recommendations")!="DISABLED"
            or not isinstance(evidence.get("samples"),list)
            or evidence.get("n")!=len(evidence["samples"])):
        return result
    result["settled_evidence_count"]=len(evidence["samples"])
    result["bundesliga_two_publisher_candidate_audit"] = bundesliga_candidate_audit(
        evidence, crosscheck, now)
    # Repeated sealed prediction identifiers may not multiply verification
    # agreement metrics, even when the outcome is identical.
    key_counts = defaultdict(int)
    for sample in evidence["samples"]:
        if isinstance(sample,dict) and isinstance(sample.get("key"),str):
            key_counts[sample["key"]]+=1
    duplicates = {key for key,n in key_counts.items() if n>1}
    result["duplicate_evidence_samples"]=sum(key_counts[key] for key in duplicates)
    result["unique_evidence_keys_count"]=sum(n==1 for n in key_counts.values())
    if not isinstance(sources,dict):
        return result
    try:
        stamp=verify(sources)
        if not -300 <= (now-stamp).total_seconds() <= 48*3600:
            return result
    except (TypeError,KeyError,ValueError,OverflowError):
        return result
    idx=defaultdict(list)
    for item in sources["sampled_fixtures"]:
        if (item.get("provider") not in PROVIDERS or item.get("status")!="FINISHED"
                or not isinstance(item.get("score_ft"),list)):
            continue
        league=item.get("league")
        if league not in LEAGUES:continue
        h=team_id(league,item.get("home")); a=team_id(league,item.get("away"))
        if not h or not a or h==a:continue
        score=item["score_ft"]
        if len(score)!=2 or any(type(s) is not int or not 0<=s<=30 for s in score):
            continue
        outcome=0 if score[0]>score[1] else 1 if score[0]==score[1] else 2
        try:
            kickoff = utc(item["kickoff_utc"])
        except (KeyError, TypeError, ValueError, OverflowError):
            # One malformed free-provider fixture must not abort the whole audit.
            continue
        idx[(league,h,a)].append((item["provider"],kickoff,outcome,tuple(score)))
    if not idx:
        result["status"]="PARTIAL_CHECK"
        result["unmatched_samples"]=len(evidence["samples"])
        return result
    for sample in evidence["samples"]:
        if isinstance(sample,dict) and isinstance(sample.get("key"),str) and sample["key"] in duplicates:
            result["unmatched_samples"]+=1
            continue
        try:
            key=json.loads(sample["key"])
            league=sample["league"]
            kickoff=utc(sample["kickoff_utc"])
            if len(key)!=4 or key[0]!=league:
                raise ValueError("INVALID_ARCHIVED_IDENTITY")
            fixture=(league,team_id(league,key[1]),team_id(league,key[2]))
            y=sample["y"]
            if type(y) is not int or y not in (0,1,2):
                raise ValueError("INVALID_ARCHIVED_OUTCOME")
        except (ValueError,TypeError,KeyError,IndexError):
            result["unmatched_samples"]+=1
            continue
        matched=[(provider,outcome,score) for provider,date,outcome,score
                 in idx.get(fixture,[])
                 if abs((date-kickoff).total_seconds())<=45*60]
        if not matched:
            result["unmatched_samples"]+=1
            continue
        # Compare FULL-TIME SCORES, not only W/D/L. Two sources reporting
        # (1-0) and (4-0) are NOT a verified 90-minute result.
        # One provider's duplicate API rows count as one publisher only.
        votes=defaultdict(set)
        for provider,outcome,score in matched:
            votes[provider].add((outcome, score))
        if any(len(values)!=1 for values in votes.values()):
            result["conflicting_observations"]+=1
            continue
        for provider in votes:
            result["provider_counts"][provider]+=1
        values=[next(iter(v)) for v in votes.values()]
        if any(outcome!=y for outcome,_ in values):
            result["conflicting_observations"]+=1
        elif len(votes)>=2:
            if len(set(score for _,score in values))==1:
                result["two_provider_agreements"]+=1
                result["two_provider_exact_score_agreements"]+=1
            else:
                result["same_outcome_different_final_score_conflicts"]+=1
                result["conflicting_observations"]+=1
        else:
            result["single_source_agreements"]+=1
    result["status"]="PARTIAL_CHECK"
    return result


def publish(site, evidence_path, sources_path):
    site=Path(site)
    evidence=json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    src=json.loads(Path(sources_path).read_text(encoding="utf-8")) if Path(sources_path).is_file() else None
    crosscheck = None
    path = site / "crosscheck.json"
    if path.is_file() and path.stat().st_size <= 150_000:
        try:
            crosscheck = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            pass
    result=compare(evidence,src,crosscheck=crosscheck)
    (site/"independent_results.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in (
        "status","settled_evidence_count","single_source_agreements",
        "two_provider_agreements","two_provider_exact_score_agreements",
        "same_outcome_different_final_score_conflicts",
        "conflicting_observations","production_recommendations")}))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    p.add_argument("--evidence",required=True)
    p.add_argument("--sources",default="sources/latest.json")
    a=p.parse_args()
    publish(a.site,a.evidence,a.sources)
