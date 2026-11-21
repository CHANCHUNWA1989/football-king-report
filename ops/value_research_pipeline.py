"""One-stop value research gate: no unverified model probability or odds."""
import argparse
import json
from pathlib import Path
from ev_screen import screen_ev
from asian_threeway_ev_research import assess as assess_asian_threeway
from total_goals_ev_research import assess as assess_goal_totals
from decimal import Decimal
import math
import re


def _normalized_market(market):
    if not isinstance(market, str):
        return ""
    return market.casefold().strip().replace("-", "_").replace(" ", "_").replace("/", "_")


def _totals_market(market):
    """Force explicit goal totals onto the payout-aware distribution path."""
    key = _normalized_market(market)
    return (
        key in ("totals", "total", "ou", "o_u", "goals", "goal_total",
                "goal_totals", "asian_totals", "asian_total", "over", "under")
        or key.startswith(("over_", "under_", "totals_", "total_",
                           "asian_totals_", "asian_total_", "asian_over_",
                           "asian_under_", "asian_ou_", "goal_total_",
                           "goal_totals_", "goals_over_", "goals_under_",
                           "ou_", "o_u_"))
        or bool(re.match(r"^(?:over|under|ou)[0-9]", key))
    )


def _market_embedded_total_line(market):
    """Read an explicit totals threshold suffix, never infer one if absent."""
    key = _normalized_market(market)
    match = re.search(r"(?:^|_)([0-9]+)(?:[_.]([0-9]+))?$", key)
    if not match:
        match = re.fullmatch(r"(?:over|under|ou)([0-9]+)(?:\\.([0-9]+))?", key)
    if not match:
        return None
    whole, fraction = match.groups()
    if len(whole) > 4 or (fraction is not None and len(fraction) > 4):
        return "INVALID"
    return Decimal(whole + ("." + fraction if fraction is not None else ""))


def _totals_research(row):
    raw_side, raw_selection = row.get("side"), row.get("selection")
    claimed_sides = [v.upper() for v in (raw_side, raw_selection)
                     if isinstance(v, str) and v.upper() in ("OVER", "UNDER")]
    invalid_side = (any(v is not None and
                        (not isinstance(v, str) or v.upper() not in ("OVER", "UNDER"))
                        for v in (raw_side, raw_selection))
                    or len(set(claimed_sides)) != 1)
    market_tokens = _normalized_market(row.get("market")).split("_")
    hinted_sides = {token.upper() for token in market_tokens
                    if token in ("over", "under")}
    # Compact aliases such as "over2.75" still bind market direction.
    market_key = _normalized_market(row.get("market"))
    for label in ("over", "under"):
        if re.match(r"^" + label + r"[0-9]", market_key):
            hinted_sides.add(label.upper())
    if len(hinted_sides) > 1 or (hinted_sides and set(claimed_sides) != hinted_sides):
        invalid_side = True
    if invalid_side:
        return {
            "research_candidate": False,
            "blockers": ["TOTAL_MARKET_SELECTION_CONFLICT_OR_MISSING"],
            "production_recommendations": "DISABLED",
        }
    embedded_line = _market_embedded_total_line(row.get("market"))
    declared_line = row.get("line")
    if (embedded_line == "INVALID" or
            (embedded_line is not None and type(declared_line) in (int, float)
             and math.isfinite(declared_line)
             and embedded_line != Decimal(str(declared_line)))):
        return {
            "research_candidate": False,
            "blockers": ["TOTAL_MARKET_LINE_MISMATCH"],
            "production_recommendations": "DISABLED",
        }
    scenario = assess_goal_totals(
        row.get("goal_total_probabilities"),
        side=claimed_sides[0],
        line=row.get("line"),
        decimal_odds=row.get("odds"),
        conservative_goal_lower_bounds=row.get("conservative_goal_total_lower_bounds"),
        quote_age_seconds=row.get("quote_age_seconds"),
    )
    reason = scenario["reason"]
    if scenario["research_value_screen_pass"]:
        reason = "TOTAL_MATH_ONLY_NOT_INDEPENDENTLY_CERTIFIED"
    return {
        "research_candidate": False,
        "blockers": [reason],
        "total_goals_research_scenario": scenario,
        "production_recommendations": "DISABLED",
    }


def _asian_market(market):
    """Treat explicitly named Asian spread/handicap markets as non-binary."""
    if not isinstance(market, str):
        return False
    key = market.casefold().strip().replace("-", "_").replace(" ", "_")
    return ("asian" in key or "handicap" in key or "spread" in key
            or key in ("ah", "hdp"))


def _asian_research(row):
    # This accepts only three-way probability claims on near-zero spreads.
    # Even a math-screen PASS has no evidence of an executable quotation or
    # calibrated bound, and must NEVER be surfaced as a bet candidate.
    scenario = assess_asian_threeway(
        row.get("threeway_probabilities"),
        side=row.get("side"),
        handicap=row.get("line"),
        decimal_odds=row.get("odds"),
        lower_bounds_home_draw_away=row.get("conservative_threeway_lower_bounds"),
        quote_age_seconds=row.get("quote_age_seconds"),
    )
    reason = scenario["reason"]
    if scenario["research_value_screen_pass"]:
        reason = "ASIAN_MATH_ONLY_NOT_INDEPENDENTLY_CERTIFIED"
    return {
        "research_candidate": False,
        "blockers": [reason],
        "asian_research_scenario": scenario,
        "production_recommendations": "DISABLED",
    }


def evaluate(rows):
    if not isinstance(rows,list):
        raise ValueError("INVALID_ROWS")
    results=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("INVALID_ROW")
        identity={k:row.get(k) for k in ("fixture_id","market","selection")}
        if _totals_market(row.get("market")):
            result = _totals_research(row)
        elif _asian_market(row.get("market")):
            result = _asian_research(row)
        elif not isinstance(row.get("odds"),(float,int)) or not isinstance(row.get("probability"),(float,int)):
            result={"research_candidate":False,"blockers":["MISSING_ODDS_OR_PROBABILITY"],"production_recommendations":"DISABLED"}
        else:
            result=screen_ev(row["odds"],row["probability"],
                calibrated=row.get("calibrated") is True,
                fresh_odds=row.get("fresh_odds") is True)
        results.append({**identity,**result})
    return {"schema":"football-king-value-research-v1",
        "status":"RESEARCH_ONLY",
        "total":len(results),
        "candidate_count":sum(x["research_candidate"] for x in results),
        "results":results,
        "production_recommendations":"DISABLED"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=evaluate(json.loads(Path(args.input).read_text(encoding="utf-8")))
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Research candidates:",report["candidate_count"],"/",report["total"])

if __name__=="__main__":
    main()
