"""Research-only post-match review of *unsealed* conversational selections.

This is not the prospective forecast journal. Chat summaries, ordered claims,
historic reference prices, and linked match reports cannot retrospectively
prove pre-kickoff creation, a tradable offer, or an authentic settled result.
Never write these records into evidence/settled.json or forecast_decision_journal.
"""
import argparse
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

from asian_handicap_research import grade as handicap_grade, split_lines

SCHEMA = "football-king-unsealed-chat-postmatch-v1"
SOURCE = "POSTMATCH_CHAT_RECAP_UNVERIFIED"
GRADES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")
MAX_RECORDS = 100
MAX_VERSIONS = 20


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _valid_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 1500:
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and not parsed.username and not parsed.password
                and not parsed.fragment and not parsed.port)
    except ValueError:
        return False


def _version(value):
    _require(isinstance(value, dict), "INVALID_REPORTED_VERSION")
    _require(set(value) in (
        {"market", "direction", "line"},
        {"market", "direction", "line", "unverified_reference_price"}),
        "INVALID_REPORTED_VERSION_FIELDS")
    market, direction, line = (value.get(key) for key in ("market", "direction", "line"))
    _require(market in ("totals", "asian_handicap"), "UNSUPPORTED_MARKET")
    _require(type(line) in (float, int) and math.isfinite(line),
             "INVALID_REPORTED_LINE")
    if market == "totals":
        _require(direction in ("OVER", "UNDER") and .25 <= line <= 15,
                 "INVALID_TOTAL_DIRECTION_OR_LINE")
    else:
        _require(direction in ("HOME", "AWAY") and -10 <= line <= 10,
                 "INVALID_HANDICAP_DIRECTION_OR_LINE")
    split_lines(line)  # exact quarter line, no invented handicap
    if "unverified_reference_price" in value:
        odds = value["unverified_reference_price"]
        _require(type(odds) in (float, int) and math.isfinite(odds)
                 and 1.01 <= odds <= 100, "INVALID_REFERENCE_PRICE_CLAIM")
    return market, direction, line


def _grade(score, version):
    h, a = score
    market, direction, line = _version(version)
    if market == "asian_handicap":
        return handicap_grade(h, a, direction, line)
    units = split_lines(line)  # each is an integer quarter unit
    total_quarters = 4 * (h + a)
    result = [
        (1 if total_quarters > unit else -1 if total_quarters < unit else 0)
        if direction == "OVER" else
        (1 if total_quarters < unit else -1 if total_quarters > unit else 0)
        for unit in units
    ]
    return {2: "FULL_WIN", 1: "HALF_WIN", 0: "PUSH",
            -1: "HALF_LOSS", -2: "FULL_LOSS"}[sum(result)]


def audit(records):
    """Only conditional grades of reported last picks; never authenticate."""
    _require(isinstance(records, list) and len(records) <= MAX_RECORDS,
             "INVALID_UNSEALED_CHAT_RECAP")
    outcomes = {name: 0 for name in GRADES}
    seen = set()
    cases = []
    reversals = 0
    total_versions = 0
    unverified_prices = 0
    for item in records:
        _require(isinstance(item, dict) and set(item) == {
            "fixture_ref", "source_evidence", "result_source_url",
            "score_ft", "versions"}, "INVALID_RECAP_FIELDS")
        ref = item["fixture_ref"]
        _require(type(ref) is str and 1 <= len(ref.strip()) <= 140,
                 "INVALID_FIXTURE_REFERENCE")
        _require(ref not in seen, "DUPLICATE_FIXTURE_REFERENCE")
        seen.add(ref)
        _require(item["source_evidence"] == SOURCE, "UNVERIFIED_RECAP_SOURCE_ONLY")
        _require(_valid_url(item["result_source_url"]), "INVALID_RESULT_REFERENCE_URL")
        score = item["score_ft"]
        _require(type(score) is list and len(score) == 2
                 and all(type(g) is int and 0 <= g <= 30 for g in score),
                 "INVALID_REPORTED_FINAL_SCORE")
        versions = item["versions"]
        _require(type(versions) is list and 1 <= len(versions) <= MAX_VERSIONS,
                 "INVALID_CLAIMED_VERSION_LIST")
        selections = [_version(version) for version in versions]
        _require(all(first != second for first, second in
                     zip(selections, selections[1:])),
                 "DUPLICATE_CONSECUTIVE_VERSION_CLAIM")
        changes = sum(a != b for a, b in zip(selections, selections[1:]))
        reversals += int(changes > 0)
        total_versions += len(versions)
        unverified_prices += sum("unverified_reference_price" in x for x in versions)
        last = versions[-1]
        grade = _grade(score, last)
        outcomes[grade] += 1
        cases.append({
            "fixture_ref": ref,
            "claimed_result_reference_url": item["result_source_url"],
            "reported_score_ft": list(score),
            "reported_version_count": len(versions),
            "directions_reported_in_order": [v["direction"] for v in versions],
            "last_claimed_market": last["market"],
            "last_claimed_line": last["line"],
            "last_claimed_direction": last["direction"],
            "grade_if_reported_score_is_correct": grade,
            "version_order_independently_authenticated": False,
            "result_independently_authenticated": False,
            "offered_market_line_authenticated": False,
            "quote_executable_verified": False,
            "count_as_formal_bet": False,
        })
    return {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY" if cases else "HOLD",
        "source_status": SOURCE,
        "case_count": len(cases),
        "total_claimed_versions": total_versions,
        "changed_direction_cases": reversals,
        "unverified_reference_price_claims": unverified_prices,
        "last_version_grades": outcomes,
        "cases": cases,
        "sealed_prematch_forecasts": False,
        "original_message_times_authenticated": False,
        "independently_verified_results": False,
        "executable_prices_authenticated": False,
        "can_enter_formal_settlement_ledger": False,
        "certified_forward_samples": 0,
        "formal_bet_count": 0,
        "roi": None,
        "ev": None,
        "model_was_used_for_original_pick_verified": False,
        "no_retroactive_prematch_seal": True,
        "production_recommendations": "DISABLED",
        "notice_zh": (
            "只作事後對話研究聲稱嘅條件式盤口結算；"
            "冇原始訊息時刻／賽前封存／可成交盤口同獨立賽果認證，"
            "不可計入正式往績、正EV或ROI。"
        ),
    }


def publish(input_path, output_path):
    src, dst = Path(input_path), Path(output_path)
    _require(src.resolve() != dst.resolve(), "WILL_NOT_OVERWRITE_ORIGINAL_CLAIMS")
    _require(src.stat().st_size <= 1_000_000, "OVERSIZE_RECAP_INPUT")
    data = json.loads(src.read_text(encoding="utf-8"))
    report = audit(data)
    dst.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                              allow_nan=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Unsealed chat-recap JSON list")
    parser.add_argument("--output", required=True, help="Research-only report JSON")
    args = parser.parse_args()
    report = publish(args.input, args.output)
    print(json.dumps({
        "status": report["status"], "case_count": report["case_count"],
        "last_version_grades": report["last_version_grades"],
        "certified_forward_samples": 0,
        "production_recommendations": "DISABLED",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
