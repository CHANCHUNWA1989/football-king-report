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
                p_at, m_at, ko = (iso(row["prediction_utc"]), iso(row["market_snapshot_utc"]),
                                  iso(row["kickoff_utc"]))
                if not (m_at <= p_at <= ko - timedelta(minutes=10)):
                    continue
                # Same maximum baseline lag as the live snapshot pairing gate.
                if (p_at - m_at).total_seconds() > 750 * 60:
                    continue
                if not (len(row["model"]) == len(row["market"]) == 3):
                    continue
                if not all(type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 1 for v in row["model"] + row["market"]):
                    continue
                if abs(sum(row["model"]) - 1) > .002 or abs(sum(row["market"]) - 1) > .002:
                    continue
                key = (str(row["league"]), identity(row["home"]), identity(row["away"]), ko.isoformat())
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
            # Earliest sealed forecast only (no favorable late prediction cherry-picking).
            if key not in selected or p_at < iso(selected[key]["prediction_utc"]):
                selected[key] = row
            if len(selected) > MAX_EVIDENCE:
                raise ValueError("TOO_MANY_UNIQUE_FORECASTS")
    return list(selected.items())


def _score(match):
    if not isinstance(match, dict) or match.get("status") != "FINISHED":
        return None
    score = match.get("score_ft")
    if (not isinstance(score, list) or len(score) != 2
            or not all(type(x) is int and 0 <= x <= 30 for x in score)):
        return None
    return 0 if score[0] > score[1] else 1 if score[0] == score[1] else 2


def build_index(report, now, source_results=None):
    """Use only per-league identified finished 90-minute results."""
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
    output = {}
    for row in items + sources:
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
        entry = (kickoff, y, local_day)
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
                or key[1] == key[2]):
            return False
        kickoff = iso(row["kickoff_utc"])
        forecast = iso(row["forecast_utc"])
        market = iso(row["market_utc"])
        if (iso(key[3]) != kickoff or not market <= forecast <= kickoff - timedelta(minutes=10)
                or forecast - market > timedelta(minutes=750)):
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


def extend(previous, archived, public_report, source_results=None):
    """Returns evidence with no duplicates and a count of new settled fixtures."""
    now = iso(public_report["checked_utc"])
    fixtures = build_index(public_report, now, source_results)
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
        for event, result, local_day in fixtures.get(fixture_key, []):
            if event is not None:
                suitable = abs((event - ko).total_seconds()) <= 45 * 60
            else:
                # For date-only scores, require identical local HK match day.
                suitable = local_day == target_day
            if suitable:
                matches.append((event, result, local_day))
        # Multiple competing finals are not arbitrarily resolved.
        if len(matches) != 1:
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
        if (isinstance(ab, list) and len(ab) == 3
                and all(type(x) in (float, int) and __import__("math").isfinite(x) and 0 <= x <= 1 for x in ab)
                and abs(sum(ab) - 1) < .002
                and record.get("ab_model") == "probability-shrink-to-uniform-fixed-0.15-v1"):
            sample["ab"] = ab
            sample["ab_model"] = record["ab_model"]
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
        if isinstance(ab,list) and len(ab)==3:
            try:
                ko=iso(source["kickoff_utc"])
                if all(__import__("math").isfinite(v) and 0 <= v <= 1 for v in ab) and abs(sum(ab)-1)<.002:
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
            output="settled-next.json", result_input=None):
    site = Path(site)
    report = json.loads((site / "report.json").read_text(encoding="utf-8"))
    old = json.loads(Path(previous).read_text(encoding="utf-8")) if Path(previous).is_file() else {}
    results = (json.loads(Path(result_input).read_text(encoding="utf-8"))
               if result_input and Path(result_input).is_file() else None)
    evidence = extend(old, load_archived(archives), report, results)
    metrics = report_metrics(evidence)
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
    args = parser.parse_args()
    print(json.dumps(publish(args.site, args.archives, args.previous, args.output,
                             args.result_input), ensure_ascii=False))
