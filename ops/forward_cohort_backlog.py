"""Research-only audit of genuine sealed pre-match pairs waiting for a final score.

Never settles or rewrites observations. It reuses exactly the production
forward index and strict league-scoped kickoff matching, not a new data feed.
No bookmaker prices, forecast probabilities or betting instructions published.
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from forward_validation import (
    build_index, load_archived, valid_prior_sample, iso, MAX_EVIDENCE,
)
from model_ab import matches_sealed as valid_b
from model_market_challenger import matches_sealed as valid_c
from team_identity import team_id

HK = ZoneInfo("Asia/Hong_Kong")
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
LABELS = {
    "epl": "英超", "championship": "英冠", "bundesliga": "德甲",
    "laliga": "西甲", "seriea": "意甲", "ligue1": "法甲",
}
STATES = (
    "SETTLED_RESEARCH_ONLY", "AWAITING_FULL_TIME_PLUS_TWO_HOURS",
    "WAITING_FOR_MATCHED_FINISHED_SCORE", "AMBIGUOUS_FINISHED_SCORE",
    "SOURCE_HAS_FINAL_NOT_IN_SETTLED_LEDGER",
)


def _matches(index, league, record, kickoff):
    home = team_id(league, record.get("home"))
    away = team_id(league, record.get("away"))
    if not home or not away or home == away:
        return []
    matches = []
    for event, outcome, local_day in index.get((league, home, away), []):
        if event is not None:
            consistent = abs((event - kickoff).total_seconds()) <= 45 * 60
        else:
            consistent = local_day == kickoff.astimezone(HK).date()
        if consistent:
            matches.append((event, outcome, local_day))
    return matches


def audit(archived, evidence, report, source_results=None):
    """Classify each distinct sealed forecast into source/result bottlenecks."""
    if (not isinstance(evidence, dict)
            or evidence.get("production_recommendations") != "DISABLED"
            or evidence.get("results_independently_verified") is not False
            or not isinstance(report, dict)
            or report.get("production_recommendations") != "DISABLED"
            or not isinstance(archived, list)
            or len(archived) > MAX_EVIDENCE):
        raise ValueError("UNSAFE_COHORT_AUDIT_INPUT")
    now = iso(report["checked_utc"])
    samples = evidence.get("samples")
    if (not isinstance(samples, list) or len(samples) > MAX_EVIDENCE
            or type(evidence.get("n")) is not int
            or evidence["n"] != len(samples)):
        raise ValueError("INVALID_SETTLEMENT_LEDGER_COUNT")
    seen = set()
    settled = {}
    for row in samples:
        if not valid_prior_sample(row) or row["key"] in settled:
            raise ValueError("INVALID_OR_DUPLICATE_SETTLED_EVIDENCE")
        settled[row["key"]] = row
    index = build_index(report, now, source_results)
    groups = {league: Counter() for league in LEAGUES}
    archived_keys = set()
    fourway_pairs = 0
    c_pairs = 0
    for item in archived:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("BAD_ARCHIVED_RECORD_SHAPE")
        key, record = item
        if (not isinstance(key, tuple) or len(key) != 4
                or not isinstance(record, dict) or key[0] not in LEAGUES):
            raise ValueError("BAD_ARCHIVED_IDENTITY")
        league = key[0]
        token = json.dumps(key, ensure_ascii=False)
        if token in archived_keys:
            raise ValueError("DUPLICATE_ARCHIVE_PAIR")
        archived_keys.add(token)
        ko = iso(record["kickoff_utc"])
        b = valid_b(record.get("model"), record.get("ab"), record.get("ab_model"))
        c = valid_c(record.get("model"), record.get("market"),
                    record.get("c"), record.get("c_model"))
        c_pairs += int(c)
        fourway_pairs += int(b and c)
        counts = groups[league]
        counts["sealed_pairs"] += 1
        counts["sealed_c_challengers"] += int(c)
        counts["sealed_ab_c_market_same_case"] += int(b and c)
        if token in settled:
            counts["SETTLED_RESEARCH_ONLY"] += 1
        elif now < ko + timedelta(minutes=120):
            counts["AWAITING_FULL_TIME_PLUS_TWO_HOURS"] += 1
        else:
            candidates = _matches(index, league, record, ko)
            if not candidates:
                counts["WAITING_FOR_MATCHED_FINISHED_SCORE"] += 1
            elif len(candidates) > 1:
                counts["AMBIGUOUS_FINISHED_SCORE"] += 1
            else:
                counts["SOURCE_HAS_FINAL_NOT_IN_SETTLED_LEDGER"] += 1
    for record in samples:
        group = groups[record["league"]]
        group["c_settled"] += int(valid_c(record.get("p"), record.get("m"),
                                         record.get("c"), record.get("c_model")))
        group["ab_c_market_settled"] += int(
            valid_b(record.get("p"), record.get("ab"), record.get("ab_model"))
            and valid_c(record.get("p"), record.get("m"),
                        record.get("c"), record.get("c_model")))
        group["settled_ledger_cases"] += 1
    by_league = []
    for league in LEAGUES:
        c = groups[league]
        by_league.append({
            "league": league, "label": LABELS[league],
            "sealed_unique_pairs": c["sealed_pairs"],
            "settled_ledger_cases": c["settled_ledger_cases"],
            "pending_kickoff_or_two_hour_window": c["AWAITING_FULL_TIME_PLUS_TWO_HOURS"],
            "score_unavailable_or_unmatched": c["WAITING_FOR_MATCHED_FINISHED_SCORE"],
            "ambiguous_finished_score": c["AMBIGUOUS_FINISHED_SCORE"],
            "finished_score_observed_not_yet_settled": c["SOURCE_HAS_FINAL_NOT_IN_SETTLED_LEDGER"],
            "sealed_c_pairs": c["sealed_c_challengers"],
            "sealed_ab_c_market_pairs": c["sealed_ab_c_market_same_case"],
            "settled_c_cases": c["c_settled"],
            "settled_fourway_cases": c["ab_c_market_settled"],
            "remaining_to_40_settled": max(0, 40-c["settled_ledger_cases"]),
            "results_independently_verified": False,
        })
    missing = sum(c["WAITING_FOR_MATCHED_FINISHED_SCORE"] for c in groups.values())
    ambiguous = sum(c["AMBIGUOUS_FINISHED_SCORE"] for c in groups.values())
    ready = sum(c["SOURCE_HAS_FINAL_NOT_IN_SETTLED_LEDGER"] for c in groups.values())
    return {
        "schema": "football-king-forward-cohort-backlog-v1",
        "as_of_utc": now.isoformat(),
        "status": "RESEARCH_ONLY",
        "archived_distinct_pre_match_pairs": len(archived),
        "settled_forward_cases": len(samples),
        "unverified_settlement_cases": len(samples),
        "certified_independent_settlement_cases": 0,
        "minimum_required_forward_cases": 300,
        "remaining_to_300": max(0, 300-len(samples)),
        "sealed_c_pair_count": c_pairs,
        "sealed_same_case_a_b_c_market_pairs": fourway_pairs,
        "unmatched_finished_result_backlog": missing,
        "ambiguous_finished_result_backlog": ambiguous,
        "score_observed_pending_settlement": ready,
        "by_league": by_league,
        "input_sources_are_not_independently_certified": True,
        "all_published_counts_research_only": True,
        "market_odds_executable": False,
        "recommendations_authorized": 0,
        "production_recommendations": "DISABLED",
        "warning": (
            "Archive counts are not independent scores, profitable wagers or"
            " certification. Only sealed, prior-market forecasts can be"
            " considered; late and ambiguous scores remain pending."
        ),
    }


def render(result):
    """Simple bounded HTML counts from fixed labels, never user/source HTML."""
    rows = "".join(
        "<tr><td>" + LABELS[p["league"]] + "</td>"
        + "".join("<td>" + str(p[name]) + "</td>" for name in (
            "sealed_unique_pairs", "settled_ledger_cases",
            "score_unavailable_or_unmatched", "ambiguous_finished_score",
            "settled_fourway_cases"
        )) + "</tr>"
        for p in result["by_league"])
    return (
        '<section id="forward-cohort-backlog">'
        '<h2>賽前封存與賽後結算瓶頸｜六大聯賽</h2>'
        '<p>封存對照：' + str(result["archived_distinct_pre_match_pairs"])
        + ' 場｜初步結算：' + str(result["settled_forward_cases"])
        + ' 場｜距300場仲差：' + str(result["remaining_to_300"])
        + ' 場｜獨立認證：0 場。</p>'
        '<table><thead><tr><th>聯賽</th><th>已封存</th>'
        '<th>初步結算</th><th>缺完場比分</th><th>比分有歧義</th>'
        '<th>A/B/C/市場同場結算</th></tr></thead><tbody>'
        + rows + '</tbody></table>'
        '<p class="small">已封存≠已完場；初步結算≠獨立驗證。'
        '所有同場對照只係 Shadow 研究，唔係正式投注推薦。'
        '<a href="forward_cohort_backlog.json">查看詳細待處理樣本及新模型覆蓋</a></p>'
        '</section>'
    )


def publish(site, evidence, archives="research_pairs", source_file=None):
    site = Path(site)
    ledger = json.loads(Path(evidence).read_text(encoding="utf-8"))
    report = json.loads((site/"report.json").read_text(encoding="utf-8"))
    source = None
    if source_file and Path(source_file).is_file():
        source = json.loads(Path(source_file).read_text(encoding="utf-8"))
    result = audit(load_archived(archives), ledger, report, source)
    (site/"forward_cohort_backlog.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    page = site / "index.html"
    html = page.read_text(encoding="utf-8")
    if 'id="forward-cohort-backlog"' in html:
        raise ValueError("DUPLICATE_FORWARD_COHORT_SECTION")
    anchor = "<h2>近期賽程與賽果</h2>"
    if anchor in html:
        html = html.replace(anchor, render(result)+anchor, 1)
    elif "</main>" in html:
        html = html.replace("</main>", render(result)+"</main>", 1)
    else:
        raise ValueError("NO_SAFE_REPORT_SECTION")
    page.write_text(html, encoding="utf-8")
    return result


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    p.add_argument("--archives", default="research_pairs")
    p.add_argument("--evidence", required=True)
    p.add_argument("--source-file", default=None)
    args=p.parse_args()
    output=publish(args.site,args.evidence,args.archives,args.source_file)
    print(json.dumps({k:output[k] for k in (
        "archived_distinct_pre_match_pairs", "settled_forward_cases",
        "remaining_to_300", "unmatched_finished_result_backlog",
        "score_observed_pending_settlement", "production_recommendations"
    )},ensure_ascii=False))
