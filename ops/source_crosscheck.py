"""Cross-check one overlapping league across independent public publishers.

Cross-checking a subset of Bundesliga results is not certification of other
leagues, timestamps, betting prices or model accuracy.
"""
import argparse
import json
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def normalized_team(value):
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in value if not unicodedata.combining(c) and c.isalnum())


def _day(row):
    return date.fromisoformat(row["date"])


def compare(first, second):
    """Only exact normalized home-away team identities within one calendar day."""
    valid_a = []
    valid_b = []
    for destination, rows in ((valid_a, first), (valid_b, second)):
        for r in rows:
            if not isinstance(r, dict):
                continue
            try:
                day = _day(r)
                h, a = normalized_team(r["home"]), normalized_team(r["away"])
            except (ValueError, KeyError, TypeError):
                continue
            if h and a and h != a:
                destination.append((day, h, a, r))
    found, score_comparisons, conflicts, differences, used_b = 0, 0, 0, [], set()
    for d, h, a, r in valid_a:
        pairs = [(j, row) for j, (otherday, home, away, row) in enumerate(valid_b)
                 if j not in used_b and h == home and a == away
                 and abs((d - otherday).days) <= 1]
        if len(pairs) != 1:
            continue
        j, other = pairs[0]
        used_b.add(j)
        found += 1
        score_one, score_two = r.get("score_ft"), other.get("score_ft")
        if isinstance(score_one, list) and len(score_one) == 2 and isinstance(score_two, list) and len(score_two) == 2:
            score_comparisons += 1
            if score_one != score_two:
                conflicts += 1
                if len(differences) < 10:
                    differences.append({
                        "date": d.isoformat(), "home": str(r["home"])[:90],
                        "away": str(r["away"])[:90], "source_a_score": score_one,
                        "source_b_score": score_two,
                    })
    return {"matched_identical_home_away": found, "score_comparisons": score_comparisons,
            "score_conflicts": conflicts, "conflict_examples": differences,
            "not_compared_or_mismatched_teams_a": len(valid_a) - found,
            "not_compared_or_mismatched_teams_b": len(valid_b) - found}


def validate_site(site, comparison):
    site = Path(site)
    quality_path, status_path, report_path = (site / "quality.json", site / "status.json", site / "report.json")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    quality["independent_bundesliga_result_comparisons"] = comparison.get("score_comparisons", 0)
    quality["independent_bundesliga_matched_fixtures"] = comparison.get("matched_identical_home_away", 0)
    quality["independently_verified_all_leagues"] = False
    if comparison.get("score_conflicts", 0):
        quality["critical_errors"] = sorted(set(quality.get("critical_errors", []) +
                                                 ["INDEPENDENT_RESULT_SOURCE_CONFLICT"]))
        quality["status"] = status["status"] = report["status"] = status["quality_status"] = "HOLD"
    elif comparison.get("score_comparisons", 0) == 0:
        quality["warnings"] = sorted(set(quality.get("warnings", []) +
                                          ["NO_INDEPENDENT_COMPARABLE_RESULTS"]))
        status["quality_warnings"] = quality["warnings"]
    else:
        quality["warnings"] = sorted(set(quality.get("warnings", []) +
                                          ["ONLY_ONE_LEAGUE_SUBSET_HAS_INDEPENDENT_CHECK"]))
        status["quality_warnings"] = quality["warnings"]
    status["quality_errors"] = quality.get("critical_errors", [])
    (site / "crosscheck.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for p, content in ((quality_path, quality), (status_path, status), (report_path, report)):
        p.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return comparison


def check(site, now=None, fetch_first=None, fetch_second=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    season_year = now.year if now.month >= 7 else now.year - 1
    season = f"{season_year}-{(season_year+1)%100:02d}"
    if fetch_first is None or fetch_second is None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        from fixture_gateway import fetch_openligadb
        from openfootball import fetch as openfootball_fetch
        fetch_first = fetch_first or fetch_openligadb
        fetch_second = fetch_second or openfootball_fetch
    failures = []
    raw = []
    for source, getter in (("OpenLigaDB", fetch_first), ("OpenFootball", fetch_second)):
        try:
            result = getter(season, "bundesliga", clock=lambda: now)
            if result.get("status") != "READY_RESEARCH" or not result.get("matches"):
                raise ValueError("NO_USABLE_SOURCE")
            raw.append(result["matches"])
        except (TypeError, ValueError, OSError, KeyError, OverflowError) as exc:
            failures.append(source + "_" + type(exc).__name__)
            raw.append([])
    compared = compare(*raw)
    compared.update({
        "status": "CONFLICT" if compared["score_conflicts"] else
                  "INCONCLUSIVE" if failures or compared["score_comparisons"] == 0 else "PARTIAL_CHECK",
        "league": "bundesliga", "sources": ["OpenLigaDB", "OpenFootball"],
        "errors": failures,
        "as_of_utc": now.isoformat(),
        "all_leagues_verified": False,
        "independent_kickoff_verification": False,
        "production_recommendations": "DISABLED",
    })
    return validate_site(site, compared)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    args = p.parse_args()
    print(json.dumps(check(args.site), ensure_ascii=False))
