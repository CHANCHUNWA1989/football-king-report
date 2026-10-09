"""Independently check published GitHub Pages quality and freshness."""
import argparse
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def parse_utc(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)


def evaluate(status, quality, now=None, max_age_hours=10):
    now = now or datetime.now(timezone.utc)
    failures = []
    if not isinstance(status, dict) or not isinstance(quality, dict):
        return {"ok": False, "failures": ["INVALID_JSON_OBJECT"]}
    try:
        if status.get("checked_utc") != quality.get("checked_utc"):
            failures.append("STATUS_QUALITY_TIME_MISMATCH")
        age_hours = (now - parse_utc(status["checked_utc"])).total_seconds() / 3600
        if not (-5 / 60 <= age_hours <= max_age_hours):
            failures.append("PUBLISHED_REPORT_STALE_OR_FUTURE")
    except (ValueError, KeyError, TypeError, OverflowError):
        age_hours = None
        failures.append("PUBLISHED_TIME_INVALID")
    if status.get("production_recommendations") != "DISABLED":
        failures.append("UNSAFE_RECOMMENDATIONS_ENABLED")
    if status.get("status") not in ("RESEARCH_ONLY", "HOLD"):
        failures.append("INVALID_PUBLIC_STATUS")
    if status.get("status") == "HOLD":
        failures.append("PUBLIC_SOURCE_HOLD")
    if status.get("quality_status") != quality.get("status"):
        failures.append("QUALITY_STATUS_MISMATCH")
    if quality.get("critical_errors"):
        failures.append("QUALITY_CRITICAL_ERROR")
    return {
        "ok": not failures,
        "failures": sorted(set(failures)),
        "published_checked_utc": status.get("checked_utc"),
        "published_age_hours": round(age_hours, 2) if age_hours is not None else None,
        "research_only": True,
        "production_recommendations": "DISABLED",
    }


def evaluate_research_layers(crosscheck, shadow, validation):
    """Check every published research-only layer; do not mistake HTTP 200 for safety."""
    errors = []
    if crosscheck.get("production_recommendations") != "DISABLED":
        errors.append("CROSSCHECK_SAFETY_FLAG")
    if crosscheck.get("status") not in ("PARTIAL_CHECK", "INCONCLUSIVE"):
        errors.append("INDEPENDENT_SOURCE_CHECK_NOT_SAFE")
    if crosscheck.get("all_leagues_verified") is not False:
        errors.append("MISLEADING_ALL_LEAGUES_VERIFIED")
    if shadow.get("production_recommendations") != "DISABLED":
        errors.append("SHADOW_SAFETY_FLAG")
    if shadow.get("model_calibrated") is not False or shadow.get("market_odds_available") is not False:
        errors.append("INVALID_SHADOW_RESEARCH_PROVENANCE")
    rows = shadow.get("predictions")
    if not isinstance(rows, list) or len(rows) != shadow.get("predictions_count"):
        errors.append("SHADOW_COUNT_MISMATCH")
    if validation.get("status") != "HOLD" or validation.get("production_recommendations") != "DISABLED":
        errors.append("INVALID_MARKET_EVIDENCE_STATE")
    return errors


def evaluate_market_layer(market_status, market_pairs, now=None):
    """Check freshness and structural safety without requiring winning bets."""
    now = now or datetime.now(timezone.utc)
    failures = []
    if not isinstance(market_status, dict) or not isinstance(market_pairs, dict):
        return ["INVALID_MARKET_LAYER"]
    if (market_status.get("production_recommendations") != "DISABLED"
            or market_pairs.get("production_recommendations") != "DISABLED"):
        failures.append("MARKET_LAYER_BETTING_SAFETY")
    if (market_status.get("status") not in ("HOLD", "RESEARCH_ONLY")
            or market_status.get("status") != market_pairs.get("status")
            or market_status.get("matched_count") != market_pairs.get("matched_count")):
        failures.append("MARKET_LAYER_STATUS_MISMATCH")
    n, m, matched = (market_status.get("model_events"), market_status.get("market_events"),
                     market_status.get("matched_count"))
    if any(type(v) is not int or v < 0 for v in (n, m, matched)):
        failures.append("INVALID_MARKET_COUNT")
    elif matched > n or matched > m:
        failures.append("MARKET_MATCH_COUNT_IMPOSSIBLE")
    if market_status.get("status") == "RESEARCH_ONLY" and matched == 0:
        failures.append("FALSE_READY_MARKET_PAIRS")
    if market_status.get("source_state") == "RESEARCH_ONLY":
        try:
            age = (now - parse_utc(market_status["market_as_of_utc"])).total_seconds()
            if not -300 <= age <= 26 * 3600:
                failures.append("DERIVED_MARKET_DATA_STALE")
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append("INVALID_MARKET_SOURCE_TIMESTAMP")
    q = market_status.get("quota")
    if q is not None and not isinstance(q, dict):
        failures.append("INVALID_QUOTA_STATUS")
    if market_pairs.get("comparisons") is not None:
        pairs = market_pairs["comparisons"]
        if not isinstance(pairs, list) or len(pairs) != matched:
            failures.append("PUBLIC_MARKET_PAIR_COUNT_MISMATCH")
    return sorted(set(failures))


def evaluate_qualification_layers(center, coverage, ab, gate, market):
    """An HTTP-successful website must never silently unlock model selections."""
    bad = []
    if any(not isinstance(x, dict) for x in (center, coverage, ab, gate, market)):
        return ["MISSING_QUALIFICATION_LAYER"]
    if (center.get("production_recommendations") != "DISABLED"
            or center.get("six_league_result_verification_complete") is not False):
        bad.append("INVALID_RESEARCH_CENTER_AUTHORIZATION")
    if (not isinstance(coverage.get("league_coverage"), list)
            or len(coverage["league_coverage"]) != 6
            or coverage.get("results_independently_verified_all_leagues") is not False
            or coverage.get("production_recommendations") != "DISABLED"):
        bad.append("INVALID_SIX_LEAGUE_COVERAGE")
    if (ab.get("promotion_allowed") is not False
            or ab.get("production_recommendations") != "DISABLED"
            or ab.get("candidate_count") != center.get("total_shadow_candidates")):
        bad.append("UNSAFE_AB_PROMOTION_OR_COUNT")
    if (gate.get("status") != "HOLD"
            or gate.get("automated_release_supported") is not False
            or gate.get("production_recommendations") != "DISABLED"
            or gate.get("model_promoted") is not False
            or gate.get("settled_samples") != center.get("total_completed_comparable_samples")):
        bad.append("QUALIFICATION_GATE_INCONSISTENT")
    if center.get("total_strict_market_pairs") != market.get("matched_count"):
        bad.append("QUALIFICATION_MARKET_PAIR_MISMATCH")
    return sorted(set(bad))


def evaluate_recommendations_layer(selections, pairs):
    """Check live research selections remain verifiable and non-executable."""
    errors = []
    if not isinstance(selections, dict) or not isinstance(pairs, dict):
        return ["INVALID_RECOMMENDATIONS_DATA"]
    if (selections.get("schema") != "football-king-explainable-research-selections-v1"
            or selections.get("selection_mode") != "SHADOW_RESEARCH_ONLY"
            or selections.get("production_recommendations") != "DISABLED"
            or selections.get("automatic_bets") is not False
            or selections.get("model_is_uncalibrated") is not True
            or selections.get("market_prices_are_not_executable") is not True
            or selections.get("validated_positive_expected_value") is not False):
        errors.append("UNSAFE_OR_MISLEADING_RECOMMENDATIONS")
    picks = selections.get("selections")
    reviews = selections.get("reviews")
    if not isinstance(picks, list) or not isinstance(reviews, list):
        return errors + ["MISSING_SELECTIONS"]
    if (selections.get("selected_count") != len(picks)
            or selections.get("paired_count") != pairs.get("matched_count")
            or len(picks) > 8):
        errors.append("RECOMMENDATIONS_PAIR_COUNT_MISMATCH")
    accepted = {v.get("case_id") for v in pairs.get("comparisons", [])
                if isinstance(v, dict)}
    if len(accepted) != pairs.get("matched_count"):
        errors.append("INVALID_PAIR_IDENTITIES")
    model_only = selections.get("model_only_watchlist")
    if (selections.get("fallback_mode") not in ("NOT_NEEDED", "MODEL_ONLY_LOW_EVIDENCE")
            or selections.get("model_only_is_betting_advice") is not False
            or not isinstance(model_only, list)
            or selections.get("model_only_count") != len(model_only or [])
            or len(model_only or []) > 5):
        errors.append("INVALID_MODEL_ONLY_FALLBACK")
    else:
        from team_identity import team_id
        shadow_keys = set()
        market_keys = {
            (x.get("league"),team_id(x.get("league"),x.get("home")),
             team_id(x.get("league"),x.get("away")),x.get("kickoff_utc"))
            for x in pairs.get("comparisons",[]) if isinstance(x,dict)
        }
        for row in model_only:
            if not isinstance(row,dict):
                errors.append("INVALID_MODEL_ONLY_EVENT")
                continue
            key=(row.get("league"),team_id(row.get("league"),row.get("home")),
                 team_id(row.get("league"),row.get("away")),row.get("kickoff_utc"))
            if key in shadow_keys or key in market_keys:
                errors.append("DUPLICATE_OR_PAIRED_MODEL_ONLY_EVENT")
            shadow_keys.add(key)
            if (row.get("reliability") != "LOW_UNVALIDATED_NO_MARKET"
                    or row.get("market_confirmed") is not False
                    or row.get("qualifies_for_betting") is not False
                    or row.get("production_recommendations") != "DISABLED"
                    or row.get("value_bet_verified") is not False
                    or row.get("executable_market_odds_available") is not False
                    or row.get("suggested_stake") is not None):
                errors.append("UNSAFE_MODEL_ONLY_RECOMMENDATIONS")
        if model_only and selections.get("fallback_mode") != "MODEL_ONLY_LOW_EVIDENCE":
            errors.append("UNEXPECTED_MODEL_ONLY_OBSERVATION")
    used = set()
    for item in picks + reviews:
        if not isinstance(item, dict):
            errors.append("NON_OBJECT_SELECTION")
            continue
        if (item.get("case_id") not in accepted
                or item.get("case_id") in used):
            errors.append("UNPAIRED_OR_DUPLICATE_SELECTION")
        used.add(item.get("case_id"))
        if (item.get("production_recommendations") != "DISABLED"
                or item.get("executable_market_odds_available") is not False
                or item.get("value_bet_verified") is not False
                or item.get("suggested_stake") is not None
                or item.get("reliability") != "UNCALIBRATED_RESEARCH_ONLY"):
            errors.append("UNSAFE_SELECTION_CONTENT")
    return sorted(set(errors))


def evaluate_optional_provider_layer(extra):
    """Additional source outages must not disable existing legal market models."""
    if not isinstance(extra, dict):
        return ["EXTRA_SOURCE_STATUS_MISSING"]
    failures = []
    providers = extra.get("providers")
    if (extra.get("schema") != "football-king-source-overlay-v1"
            or extra.get("status") not in ("HOLD", "RESEARCH_ONLY")
            or extra.get("production_recommendations") != "DISABLED"
            or extra.get("can_replace_market_1x2") is not False
            or extra.get("independently_verified_six_league_results") is not False
            or extra.get("source_samples_used_as_forecast_training") is not False
            or not isinstance(providers, list) or len(providers) != 4):
        failures.append("UNSAFE_OPTIONAL_FOOTBALL_SOURCE")
        return failures
    identities = [item.get("provider") for item in providers if isinstance(item, dict)]
    if set(identities) != {
            "thesportsdb", "api_football", "football_data_org", "sportmonks"}:
        failures.append("WRONG_OPTIONAL_SOURCE_IDENTITIES")
    if not all(type(extra.get(k)) is int and extra.get(k) >= 0 for k in
               ("matched_kickoff_agreements", "kickoff_disagreements_needing_review")):
        failures.append("INVALID_OPTIONAL_FIXTURE_COUNTS")
    return failures


def evaluate_global_free_leagues(wide):
    """Guard worldwide no-key coverage; a missing optional feed is not a pick."""
    if not isinstance(wide, dict):
        return ["GLOBAL_LEAGUE_SUMMARY_MISSING"]
    problems=[]
    if (wide.get("schema") != "football-king-global-free-league-site-v1"
            or wide.get("production_recommendations") != "DISABLED"
            or wide.get("provider_market_odds_available") is not False
            or wide.get("training_evidence_validated") is not False
            or wide.get("historic_data_can_be_presented_as_live") is not False
            or wide.get("status") not in ("HOLD", "RESEARCH_ONLY")):
        problems.append("MISLEADING_GLOBAL_LEAGUE_COVERAGE")
    items=wide.get("league_cards")
    if (not isinstance(items,list) or len(items)!=30
            or wide.get("league_file_total")!=30
            or wide.get("source_count")!=2
            or wide.get("provider_names")!=["openfootball_json","openligadb"]):
        problems.append("INVALID_GLOBAL_LEAGUE_CATALOG")
        return sorted(set(problems))
    n=0
    for row in items:
        if not isinstance(row,dict):
            problems.append("INVALID_GLOBAL_LEAGUE_ROW")
            continue
        if row.get("access_status")=="FETCHED":
            n+=1
        if (row.get("provider") not in ("openfootball_json","openligadb")
                or row.get("season_scope") not in (
                    "CURRENT_SEASON_FILE","ARCHIVED_SEASON_ONLY",
                    "2026_SEASON_REQUEST_NOT_FRESHNESS_PROOF",
                    "OPENLIGA_2026_SEASON_UNCONFIRMED",
                    "CURRENT_SEASON","ARCHIVE")
                or row.get("access_status") not in (
                    "NOT_YET_COLLECTED","FETCHED","NO_FILE_OR_ACCESS",
                    "RATE_LIMITED","NETWORK_ERROR","INVALID_SCHEMA_OR_RESPONSE",
                    "TIME_BUDGET_EXHAUSTED","HTTP_ERROR")):
            problems.append("INVALID_GLOBAL_LEAGUE_ROW")
        if (row.get("provider")=="openfootball_json"
                and row.get("precise_utc_kickoffs_confirmed",0)>0):
            problems.append("UNVERIFIED_OPENFOOTBALL_TIMEZONE")
    if n != wide.get("successful_league_files"):
        problems.append("GLOBAL_LEAGUE_COVERAGE_COUNT_MISMATCH")
    return sorted(set(problems))


def fetch_json(url):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "FootballKingPagesWatchdog/1.0"})
    with urlopen(req, timeout=15) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("PUBLIC_RESPONSE_TOO_BIG")
    return json.loads(raw)


def check_published(base_url, now=None, max_age_hours=10):
    base = base_url.rstrip("/") + "/"
    if not base.startswith("https://"):
        raise ValueError("HTTPS_REQUIRED")
    status, quality = fetch_json(base + "status.json"), fetch_json(base + "quality.json")
    result = evaluate(status, quality, now=now, max_age_hours=max_age_hours)
    extra = evaluate_research_layers(fetch_json(base + "crosscheck.json"),
                                     fetch_json(base + "shadow.json"),
                                     fetch_json(base + "validation.json"))
    market = evaluate_market_layer(fetch_json(base + "market_status.json"),
                                   fetch_json(base + "market_comparison.json"), now=now)
    final = evaluate_qualification_layers(
        fetch_json(base + "research_center.json"),
        fetch_json(base + "league_coverage.json"),
        fetch_json(base + "ab_status.json"),
        fetch_json(base + "production_gate.json"),
        fetch_json(base + "market_status.json"))
    suggestions = evaluate_recommendations_layer(
        fetch_json(base + "research_selections.json"),
        fetch_json(base + "market_comparison.json"))
    optional = evaluate_optional_provider_layer(fetch_json(base + "extra_sources.json"))
    wide = evaluate_global_free_leagues(fetch_json(base + "wide_leagues.json"))
    result["failures"] = sorted(set(result["failures"] + extra + market + final + suggestions + optional + wide))
    result["ok"] = not result["failures"]
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--max-age-hours", type=float, default=10)
    a = p.parse_args()
    try:
        result = check_published(a.base, max_age_hours=a.max_age_hours)
    except Exception as exc:
        result = {"ok": False, "failures": ["PAGE_UNAVAILABLE_OR_INVALID_" + type(exc).__name__]}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)
