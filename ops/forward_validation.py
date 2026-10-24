"""Strict forward-only settlement for archived research comparisons.

Uses only pre-existing market/model snapshots and *later* finished results.
Never uses future outcomes to construct past predictions. No executable
bookmaker odds are stored; profitability cannot be calculated from this.
"""
import argparse
import gzip
import json
import math
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from team_identity import team_id
HK=ZoneInfo("Asia/Hong_Kong")
from pathlib import Path
from market_pair import iso, identity
from model_evidence import evaluate
from model_market_challenger import MODEL as C_MODEL, matches_sealed as sealed_c_valid
from model_ab import matches_sealed as sealed_b_valid, MODEL as B_MODEL
from free_result_recovery import read_candidates as read_cached_free_finals
from free_score_history import recover as recover_historical_free_finals
from source_fixture_identity import IDENTITY_FIELDS, validate_sealed_identity

MAX_PAIR_FILES = 5000
MAX_EVIDENCE = 20000
MAX_ARCHIVE_JSON_BYTES = 8_000_000
MAX_ARCHIVE_COMPARISONS = 3000


def load_archived(root):
    """Read Git-history snapshots; rejects unlimited or malformed history."""
    root = Path(root)
    files = sorted(root.glob("**/*.json.gz")) if root.is_dir() else []
    if len(files) > MAX_PAIR_FILES:
        raise ValueError("TOO_MANY_ARCHIVED_PAIR_FILES")
    selected = {}
    # A sealed timestamp shared by conflicting predictions cannot be
    # resolved by filesystem ordering. Quarantine that timestamp, while
    # allowing an independently archived *earlier* valid record to win.
    ambiguous_at = {}
    provider_fixtures = {}
    provider_fixture_bindings = 0
    for file in files:
        if file.stat().st_size > 600000:
            raise ValueError("ARCHIVED_PAIR_TOO_LARGE")
        # A small .gz can expand to huge JSON. Enforce a decoded byte limit
        # before creating dictionaries or iterating any untrusted rows.
        with gzip.open(file, "rb") as stream:
            raw = stream.read(MAX_ARCHIVE_JSON_BYTES + 1)
        if len(raw) > MAX_ARCHIVE_JSON_BYTES:
            raise ValueError("ARCHIVE_GZIP_EXPANSION_LIMIT")
        item = json.loads(raw)
        if not isinstance(item, dict) or item.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_ARCHIVED_RECOMMENDATIONS")
        comparisons = item.get("comparisons", [])
        if not isinstance(comparisons, list) or len(comparisons) > MAX_ARCHIVE_COMPARISONS:
            raise ValueError("ARCHIVE_COMPARISON_COUNT_LIMIT")
        for row in comparisons:
            if not isinstance(row, dict) or row.get("production_recommendations") != "DISABLED":
                continue
            try:
                validate_sealed_identity(row)
                p_at, m_at, ko = (iso(row["prediction_utc"]), iso(row["market_snapshot_utc"]),
                                  iso(row["kickoff_utc"]))
                if not (m_at <= p_at <= ko - timedelta(minutes=10)):
                    continue
                # Same maximum baseline lag as the live snapshot pairing gate.
                if (p_at - m_at).total_seconds() > 750 * 60:
                    continue
                if (not isinstance(row["model"], list)
                        or not isinstance(row["market"], list)
                        or not (len(row["model"]) == len(row["market"]) == 3)):
                    continue
                if not all(type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 1 for v in row["model"] + row["market"]):
                    continue
                if abs(sum(row["model"]) - 1) > .002 or abs(sum(row["market"]) - 1) > .002:
                    continue
                # A stored B must match its fixed original formula. Null/absent
                # B fields on older legitimate snapshots remain backward
                # compatible, but any forged populated B pair is quarantined.
                has_b = isinstance(row.get("ab"), list) or row.get("ab_model") is not None
                if has_b and not sealed_b_valid(
                        row["model"], row.get("ab"), row.get("ab_model")):
                    continue
                # An archived C cannot be retrofitted after the outcome. Old
                # archives without the registered challenger remain eligible
                # for baseline A/B scoring but not for any C metrics.
                has_c = "c" in row or "c_model" in row
                if has_c and not (sealed_c_valid(
                        row["model"], row["market"], row.get("c"), row.get("c_model"))
                        and row.get("c_uses_only_prior_de_vigged_market") is True
                        and row.get("c_research_only_not_calibrated_or_executable") is True):
                    continue
                # A recorded market update must itself precede the market
                # snapshot; this prevents re-scoring a backfilled future quote.
                if row.get("market_updated_utc") is not None:
                    updated = iso(row["market_updated_utc"])
                    if not 0 <= (m_at - updated).total_seconds() <= 8 * 3600:
                        continue
                if m_at >= ko:
                    continue
                league = row["league"]
                home, away = identity(row["home"]), identity(row["away"])
                if (not isinstance(league, str) or not league.strip()
                        or not isinstance(row["home"], str)
                        or not isinstance(row["away"], str)
                        or not home or not away or home == away):
                    continue
                key = (league, home, away, ko.isoformat())
            except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
                continue
            # Inspect every valid record, including later records discarded by
            # earliest-selection. Otherwise file order can hide source-ID reuse.
            source_identity = row.get("source_fixture_identity")
            if source_identity is not None:
                source_key = (source_identity["provider"], source_identity["match_id"])
                source_keys = provider_fixtures.setdefault(source_key, set())
                if key not in source_keys:
                    # Count bindings, not just selected rows or provider IDs:
                    # many IDs for one fixture (or vice versa) are bounded too.
                    if provider_fixture_bindings >= MAX_EVIDENCE:
                        raise ValueError("TOO_MANY_SOURCE_FIXTURE_IDENTITIES")
                    source_keys.add(key)
                    provider_fixture_bindings += 1
            if key in ambiguous_at:
                # A strictly earlier forecast can supersede an ambiguous
                # later pair; otherwise all tied/conflicting rows stay out.
                if p_at >= ambiguous_at[key]:
                    continue
                del ambiguous_at[key]
            previous = selected.get(key)
            if previous is None or p_at < iso(previous["prediction_utc"]):
                selected[key] = row
            elif p_at == iso(previous["prediction_utc"]):
                # Treat precisely repeated archival snapshots as one record,
                # but never choose between different model/market contents
                # recorded for the *same earliest* prediction time.
                fields = ("model", "market", "market_snapshot_utc",
                          "market_updated_utc", "market_event_id", "ab", "ab_model",
                          "c", "c_model", "c_uses_only_prior_de_vigged_market",
                          "c_research_only_not_calibrated_or_executable", *IDENTITY_FIELDS)
                if any(previous.get(field) != row.get(field) for field in fields):
                    del selected[key]
                    ambiguous_at[key] = p_at
            if len(selected) + len(ambiguous_at) > MAX_EVIDENCE:
                raise ValueError("TOO_MANY_UNIQUE_FORECASTS")
    conflicting_keys = {key for keys in provider_fixtures.values() if len(keys) > 1 for key in keys}
    return [(key, row) for key, row in selected.items() if key not in conflicting_keys]


def _score(match):
    if not isinstance(match, dict) or match.get("status") != "FINISHED":
        return None
    score = match.get("score_ft")
    if (not isinstance(score, list) or len(score) != 2
            or not all(type(x) is int and 0 <= x <= 30 for x in score)):
        return None
    return 0 if score[0] > score[1] else 1 if score[0] == score[1] else 2


def build_index(report, now, source_results=None, free_result_rows=None, *,
                history_candidate_budget_complete=True):
    """Index matched final-score observations, retaining exact FT for conflicts."""
    items = (report.get("fixtures") or {}).get("matches") or []
    if not isinstance(items, list):
        raise ValueError("BAD_PUBLIC_FIXTURES")
    sources = []
    if isinstance(source_results, dict):
        if (source_results.get("schema") != "football-king-single-source-finished-results-1"
                or source_results.get("production_recommendations") != "DISABLED"
                or source_results.get("independently_verified_all_leagues") is not False):
            raise ValueError("INVALID_FINISHED_SOURCE_PROVENANCE")
        captured = iso(source_results["captured_utc"])
        if captured > now + timedelta(minutes=5) or now - captured > timedelta(hours=2):
            raise ValueError("FINISHED_RESULT_CAPTURE_STALE_OR_FUTURE")
        sources = source_results.get("records", [])
        if not isinstance(sources, list) or len(sources) > 4500:
            raise ValueError("TOO_MANY_FINISHED_RESULTS")
    if free_result_rows is None:
        free_result_rows = []
    if not isinstance(free_result_rows, list) or len(free_result_rows) > 150:
        raise ValueError("INVALID_CACHED_FREE_FINAL_ROWS")
    if type(history_candidate_budget_complete) is not bool:
        raise ValueError("INVALID_HISTORY_CANDIDATE_BUDGET_FLAG")
    if not history_candidate_budget_complete:
        # No source may bypass an incomplete history conflict check.
        return {}
    output = {}
    for row in items + sources + free_result_rows:
        y = _score(row)
        if y is None:
            continue
        league = row.get("league")
        if not isinstance(league, str) or not league:
            # The original V4.1 combined report lacks per-match league.
            # Never infer one; use the separately captured per-league source.
            continue
        try:
            home, away = team_id(league, row["home"]), team_id(league, row["away"])
            if not home or not away or home == away:
                continue
            kickoff = iso(row["kickoff_utc"]) if row.get("kickoff_utc") else None
            if kickoff is not None and now < kickoff + timedelta(minutes=120):
                continue
            local_day = date.fromisoformat(row["date"]) if row.get("date") else None
            if kickoff is None and local_day is None:
                continue
            key = (league, home, away)
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        # A draw (1-1) and (2-2) have the same 1X2 outcome but are
        # conflicting final scores; neither may be silently preferred.
        entry = (kickoff, y, local_day, tuple(row["score_ft"]))
        if entry not in output.setdefault(key, []):
            output[key].append(entry)
    return output

def valid_prior_sample(row):
    """Do not let a fabricated/invalid old evidence row become model truth."""
    if (not isinstance(row, dict) or row.get("production_recommendations") != "DISABLED"
            or row.get("fixture_result_source_independently_verified") is not False
            or type(row.get("y")) is not int or row["y"] not in (0, 1, 2)
            or not isinstance(row.get("key"), str)):
        return False
    try:
        key = json.loads(row["key"])
        if (not isinstance(key, list) or len(key) != 4
                or not all(isinstance(x, str) and x for x in key)
                or key[1] == key[2]
                or row.get("league") != key[0]):
            return False
        kickoff = iso(row["kickoff_utc"])
        forecast = iso(row["forecast_utc"])
        market = iso(row["market_utc"])
        if (iso(key[3]) != kickoff or not market <= forecast <= kickoff - timedelta(minutes=10)
                or forecast - market > timedelta(minutes=750)):
            return False
        if isinstance(row.get("ab"), list) or row.get("ab_model") is not None:
            if not sealed_b_valid(row.get("p"), row.get("ab"), row.get("ab_model")):
                return False
        if "c" in row or "c_model" in row:
            if not sealed_c_valid(row.get("p"), row.get("m"),
                                  row.get("c"), row.get("c_model")):
                return False
        for field in ("p", "m"):
            values = row[field]
            if (not isinstance(values, list) or len(values) != 3
                    or not all(type(v) in (float, int) and math.isfinite(v)
                               and 0 <= v <= 1 for v in values)
                    or abs(sum(values)-1) > .002):
                return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
        return False


def extend(previous, archived, public_report, source_results=None,
           free_result_rows=None, *, history_candidate_budget_complete=True):
    """Only settle on an unambiguous exact 90-minute final result."""
    now = iso(public_report["checked_utc"])
    fixtures = build_index(
        public_report, now, source_results, free_result_rows,
        history_candidate_budget_complete=history_candidate_budget_complete)
    existing = previous.get("samples", []) if isinstance(previous, dict) else []
    if not isinstance(existing, list) or len(existing) > MAX_EVIDENCE:
        raise ValueError("UNSAFE_EXISTING_EVIDENCE")
    settled = {}
    for row in existing:
        if valid_prior_sample(row):
            if row["key"] in settled and settled[row["key"]] != row:
                raise ValueError("CONFLICTING_PREVIOUS_SETTLEMENT")
            settled[row["key"]] = row
    inserted = 0
    for key, record in archived:
        # Defense in depth: direct callers must not relabel an EPL archived
        # result as another league, change teams, or substitute a later
        # kickoff. load_archived() already creates these exact identities.
        try:
            if (not isinstance(key, tuple) or len(key) != 4
                    or not isinstance(record, dict)
                    or record.get("league") != key[0]
                    or identity(record.get("home")) != key[1]
                    or identity(record.get("away")) != key[2]
                    or iso(record["kickoff_utc"]).isoformat() != key[3]):
                continue
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            continue
        unique = json.dumps(key, ensure_ascii=False)
        if unique in settled:
            continue
        ko = iso(record["kickoff_utc"])
        if now < ko + timedelta(minutes=120):
            continue
        fixture_key = (key[0], team_id(key[0], record.get("home")),
                       team_id(key[0], record.get("away")))
        if not all(fixture_key):
            continue
        target_day = ko.astimezone(HK).date()
        matches = []
        for event, result, local_day, score_ft in fixtures.get(fixture_key, []):
            if event is not None:
                suitable = abs((event - ko).total_seconds()) <= 45 * 60
            else:
                # For date-only scores, require identical local HK match day.
                suitable = local_day == target_day
            if suitable:
                matches.append((event, result, local_day, score_ft))
        # Identical final scores from separate public publishers may
        # corroborate an observation. Conflicting exact FT scores (even
        # with the same HOME/DRAW/AWAY outcome) remain quarantined.
        scores = {row[3] for row in matches}
        if len(scores) != 1:
            continue
        y = matches[0][1]
        sample = {
            "key": unique,
            "league": key[0], "kickoff_utc": ko.isoformat(),
            "forecast_utc": record["prediction_utc"],
            "market_utc": record["market_snapshot_utc"],
            "y": y,
            "p": record["model"], "m": record["market"],
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED",
        }
        ab = record.get("ab")
        if sealed_b_valid(record["model"], ab, record.get("ab_model")):
            sample["ab"] = ab
            sample["ab_model"] = record["ab_model"]
        if ("c" in record or "c_model" in record):
            if not (sealed_c_valid(record["model"], record["market"],
                                   record.get("c"), record.get("c_model"))
                    and record.get("c_uses_only_prior_de_vigged_market") is True
                    and record.get("c_research_only_not_calibrated_or_executable") is True):
                # A bad challenger must not poison the sealed baseline.
                # No C result is scored from an unvalidated archive.
                pass
            else:
                sample["c"] = record["c"]
                sample["c_model"] = C_MODEL
        settled[unique] = sample
        inserted += 1
    if len(settled) > MAX_EVIDENCE:
        raise ValueError("EVIDENCE_STORAGE_CAP_REACHED")
    result = {"schema": "football-king-forward-research-1",
              "checked_utc": now.isoformat(), "samples": list(settled.values()),
              "n": len(settled), "newly_settled": inserted,
              "results_independently_verified": False,
              "profitability_verified": False,
              "production_recommendations": "DISABLED"}
    return result


def report_metrics(evidence):
    rows = []
    for r in evidence["samples"]:
        try:
            rows.append({"kickoff": iso(r["kickoff_utc"]), "p": r["p"],
                         "m": r["m"], "y": r["y"]})
        except (KeyError, ValueError, TypeError):
            pass
    result = evaluate(rows, immutable_evidence=False)
    result.update({
        "status": "HOLD",
        "forward_archive_samples": len(rows),
        "newly_settled": evidence["newly_settled"],
        "results_independently_verified": False,
        "market_probs_from_derived_consensus_not_executable_odds": True,
        "unverified_profitability": True,
        "production_recommendations": "DISABLED",
    })
    # Same exact 90-minute outcomes and times for A/B; excluded missing older
    # snapshots are not imputed, reforecast or cherry-picked.
    ab_rows = []
    for source in evidence["samples"]:
        ab=source.get("ab")
        if sealed_b_valid(source.get("p"), ab, source.get("ab_model")):
            try:
                ko=iso(source["kickoff_utc"])
                ab_rows.append({"kickoff":ko,"p":ab,"m":source["p"],"y":source["y"]})
            except (TypeError,ValueError,KeyError):
                pass
    if ab_rows:
        ab_result=evaluate(ab_rows,immutable_evidence=False)
        if ab_result["measurements"]:
            result["ab_experiment"]={
                "status":"SHADOW_ONLY", "n":len(ab_rows),
                "variant_model":"probability-shrink-to-uniform-fixed-0.15-v1",
                "variant_log_loss":ab_result["measurements"]["model_log_loss"],
                "baseline_log_loss_same_cases":ab_result["measurements"]["market_log_loss"],
                "baseline_minus_variant_log_loss":
                    ab_result["measurements"]["market_minus_model_log_loss"],
                "promotion_allowed":False,
                "production_recommendations":"DISABLED"}
    # Evaluate C only on rows carrying its *pre-existing* sealed candidate.
    # Do not reconstruct it from the current market after games have ended.
    c_rows = []
    for source in evidence["samples"]:
        if sealed_c_valid(source.get("p"), source.get("m"),
                          source.get("c"), source.get("c_model")):
            try:
                c_rows.append({"kickoff": iso(source["kickoff_utc"]),
                               "p": source["c"], "m": source["m"], "y": source["y"]})
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
    c_status = {"status": "NO_SEALED_C_RESULTS", "n": 0, "candidate_model": C_MODEL,
                "candidate_log_loss": None, "original_model_log_loss": None,
                "market_log_loss": None, "candidate_brier": None,
                "market_brier": None, "improvement_over_market_confirmed": False,
                "selection_bias_prevented": True,
                "production_recommendations": "DISABLED"}
    if c_rows:
        scored = evaluate(c_rows, immutable_evidence=False)
        original = evaluate([
            {"kickoff": iso(r["kickoff_utc"]), "p": r["p"], "m": r["m"], "y": r["y"]}
            for r in evidence["samples"]
            if sealed_c_valid(r.get("p"), r.get("m"), r.get("c"), r.get("c_model"))
        ], immutable_evidence=False)
        a, b = scored.get("measurements"), original.get("measurements")
        if a and b:
            c_status.update({
                "status": "SHADOW_ONLY_UNVERIFIED",
                "n": len(c_rows),
                "candidate_log_loss": a["model_log_loss"],
                "original_model_log_loss": b["model_log_loss"],
                "market_log_loss": a["market_log_loss"],
                "candidate_brier": a["model_brier"],
                "original_model_brier": b["model_brier"],
                "market_brier": a["market_brier"],
                "candidate_top_choice_correct":
                    a["directional_accuracy_audit"]["model_top_choice_correct"],
                "original_model_top_choice_correct":
                    b["directional_accuracy_audit"]["model_top_choice_correct"],
                "market_top_choice_correct":
                    a["directional_accuracy_audit"]["market_top_choice_correct"],
            })
    result["fixed_market_anchored_challenger_c"] = c_status
    if len(rows) == 0:
        result["reason"] = "WAITING_FOR_SETTLED_MARKET_PAIRED_FIXTURES"
    elif len(rows) < 300:
        result["reason"] = "FORWARD_SAMPLE_UNDER_300_NOT_VALIDATED"
    else:
        # Keep evaluate()'s statistically qualified reason for mature samples.
        # publish() always exposes it and must never fail on the 300th sample.
        result["reason"] = result.get("reason") or "INDEPENDENT_VALIDATION_REQUIRED"
    return result


def publish(site, archives="research_pairs", previous="evidence/settled.json",
            output="settled-next.json", result_input=None, free_source=None,
            free_history=None):
    site = Path(site)
    report = json.loads((site / "report.json").read_text(encoding="utf-8"))
    old = json.loads(Path(previous).read_text(encoding="utf-8")) if Path(previous).is_file() else {}
    results = (json.loads(Path(result_input).read_text(encoding="utf-8"))
               if result_input and Path(result_input).is_file() else None)
    now = iso(report["checked_utc"])
    free_rows, recovery = read_cached_free_finals(free_source, now)
    remaining = max(0, 150 - len(free_rows))
    historical, historical_audit = recover_historical_free_finals(
        free_history, now, max_candidates=min(100, remaining))
    evidence = extend(old, load_archived(archives), report, results,
                      free_rows + historical,
                      history_candidate_budget_complete=historical_audit[
                          "candidate_budget_complete"])
    metrics = report_metrics(evidence)
    if not historical_audit["candidate_budget_complete"]:
        metrics["reason"] = historical_audit["reason"]
    metrics["cached_free_final_recovery"] = recovery
    metrics["cached_historical_free_final_recovery"] = historical_audit
    metrics["cached_free_final_candidates_not_independently_verified"] = True
    Path(output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (site / "validation.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    return {"n": metrics["forward_archive_samples"],
            "newly_settled": evidence["newly_settled"],
            "status": "HOLD", "reason": metrics["reason"],
            "production_recommendations": "DISABLED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    parser.add_argument("--archives", default="research_pairs")
    parser.add_argument("--previous", default="evidence/settled.json")
    parser.add_argument("--output", default="settled-next.json")
    parser.add_argument("--result-input", default=None)
    parser.add_argument("--free-source", default=None)
    parser.add_argument("--free-history", default=None)
    args = parser.parse_args()
    print(json.dumps(publish(args.site, args.archives, args.previous, args.output,
                             args.result_input, args.free_source,
                             args.free_history), ensure_ascii=False))
