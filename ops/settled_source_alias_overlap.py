"""Offline archived FT candidate overlap. Names are not native IDs or certification."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from ops.team_identity import team_id
from ops.source_publish_guard import verify, time

def key(league, home, away, kickoff):
    h, a = team_id(league, home), team_id(league, away)
    if not h or not a or h == a:
        raise ValueError("INVALID_TEAM_PAIR")
    return league, h, a, time(kickoff)

def compare(source, settled):
    collected = verify(source, now=time(source["collected_utc"]))
    if (settled.get("production_recommendations") != "DISABLED"
            or settled.get("results_independently_verified") is not False
            or settled.get("profitability_verified") is not False
            or type(settled.get("samples")) is not list
            or type(settled.get("n")) is not int
            or settled["n"] != len(settled["samples"]) or settled["n"] > 10000):
        raise ValueError("UNSAFE_SETTLED_ARCHIVE")
    index = defaultdict(list)
    seen = set()
    for row in settled["samples"]:
        if (row.get("production_recommendations") != "DISABLED"
                or row.get("fixture_result_source_independently_verified") is not False
                or type(row.get("y")) is not int or row["y"] not in (0,1,2)):
            raise ValueError("UNSAFE_SETTLED_ROW")
        parts = json.loads(row["key"])
        if (type(parts) is not list or len(parts) != 4
                or not all(type(x) is str for x in parts)
                or parts[0] != row["league"] or time(parts[3]) != time(row["kickoff_utc"])
                or not time(row["market_utc"]) <= time(row["forecast_utc"]) < time(row["kickoff_utc"])
                or row["key"] in seen):
            raise ValueError("INVALID_SETTLED_IDENTITY")
        seen.add(row["key"])
        index[key(*parts)].append(row)
    finals = [r for r in source["sampled_fixtures"] if r["status"] == "FINISHED" and r["score_ft"] is not None]
    counts = Counter((r["provider"],r["provider_event_id"]) for r in source["sampled_fixtures"])
    candidates = defaultdict(list)
    unmatched = 0
    for row in finals:
        if time(row["kickoff_utc"]) >= collected:
            raise ValueError("FUTURE_FINISHED_OBSERVATION")
        k = key(row["league"],row["home"],row["away"],row["kickoff_utc"])
        candidates[(row["provider"],k)].append(row)
    results = []
    for (provider,k), rows in candidates.items():
        matches = index.get(k, [])
        if not matches:
            unmatched += len(rows)
            continue
        if len(rows) != 1 or len(matches) != 1 or counts[(provider,rows[0]["provider_event_id"])] != 1:
            results.append({"provider":provider,"status":"AMBIGUOUS","observation_count":len(rows)})
            continue
        row, sample = rows[0], matches[0]
        home,away = row["score_ft"]
        y = 0 if home > away else 1 if home == away else 2
        results.append({"provider":provider,"provider_event_id":row["provider_event_id"],
                        "league":row["league"],"status":"OUTCOME_AGREEMENT_UNVERIFIED" if y==sample["y"] else "OUTCOME_CONFLICT",
                        "observation_count":1})
    return {"schema":"settled-source-alias-overlap-v1","archive_rows":settled["n"],
            "finished_observations":len(finals),"unmatched":unmatched,
            "candidate_records":results,"independently_verified":False,
            "authenticated_native_id_links":0,"certified_samples":0,
            "eligible_for_model_scoring":False,"status":"HOLD","production_recommendations":"DISABLED"}

if __name__ == "__main__":
    print(json.dumps(compare(json.loads(Path("sources/latest.json").read_text()),
                             json.loads(Path("evidence/settled.json").read_text())),sort_keys=True))
