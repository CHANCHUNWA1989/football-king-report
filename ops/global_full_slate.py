"""Read-only coverage ledger: account for every input row, including rejected rows.
No name-based cross-publisher identity promotion, no odds or recommendations.
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")
MAX_ROWS = 10000
MAX_BYTES = 8_000_000
DISABLED = "DISABLED"

def clock(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_CLOCK")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UNZONED_CLOCK")
    return parsed.astimezone(timezone.utc)

def safe_text(value):
    return value if isinstance(value, str) and 0 < len(value) <= 160 and value.strip() else None

def native_id(value):
    if type(value) is int and value >= 0:
        value = str(value)
    return safe_text(value)

def build(public, worldwide, shadow, world_shadow, *, now, start, end):
    if now.tzinfo is None or start.tzinfo is None or end.tzinfo is None or not start < end:
        raise ValueError("INVALID_WINDOW")
    counts = Counter()
    rows = []
    seen = set()
    native_groups = defaultdict(list)
    sources = {}
    models = set()
    for label, doc in (("core_shadow", shadow), ("world_shadow", world_shadow)):
        if not isinstance(doc, dict) or doc.get("production_recommendations") != DISABLED:
            sources[label] = "UNAVAILABLE_OR_UNSAFE"
            continue
        try:
            stamp = clock(doc["as_of_utc"])
            if not now - timedelta(hours=10) <= stamp <= now:
                raise ValueError("STALE")
            predictions = doc["predictions"]
            if not isinstance(predictions, list) or len(predictions) > MAX_ROWS:
                raise ValueError("BAD_ROWS")
        except (KeyError, TypeError, ValueError, OverflowError):
            sources[label] = "UNAVAILABLE_OR_UNSAFE"
            continue
        sources[label] = "RESEARCH_INPUT_ONLY"
        for p in predictions:
            if not isinstance(p, dict) or p.get("production_recommendations") != DISABLED:
                continue
            try:
                ko, pred = clock(p["kickoff_utc"]), clock(p["prediction_utc"])
                ident = tuple(safe_text(p.get(k)) for k in ("league", "home", "away"))
                event = native_id(p.get("event_id"))
                if all(ident) and event and pred <= stamp <= now and pred < ko:
                    models.add((label, event, ident, ko))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue

    def observe(raw, origin, league=None, fresh=False):
        counts["input_rows"] += 1
        if len(rows) >= MAX_ROWS:
            counts["not_retained_due_to_bound"] += 1
            return
        if not isinstance(raw, dict):
            raw = {}
        league = safe_text(league or raw.get("league"))
        home, away = safe_text(raw.get("home")), safe_text(raw.get("away"))
        provider = safe_text(raw.get("provider")) if origin == "worldwide" else "public_report"
        event = native_id(raw.get("provider_event_id") if origin == "worldwide" else raw.get("event_id"))
        status = safe_text(raw.get("status"))
        reasons = []
        ko = None
        try:
            ko = clock(raw.get("kickoff_utc"))
        except (TypeError, ValueError, OverflowError):
            reasons.append("MISSING_OR_INVALID_KICKOFF")
        if not all((league, home, away, provider)) or home == away:
            reasons.append("INVALID_IDENTITY")
        if not event:
            reasons.append("MISSING_NATIVE_ID")
        if not fresh:
            reasons.append("SOURCE_TIME_UNVERIFIED_OR_STALE")
        captured = None
        if raw.get("captured_utc") is not None or origin == "worldwide":
            try:
                captured = clock(raw.get("captured_utc"))
                if not now - timedelta(hours=10) <= captured <= now:
                    raise ValueError("STALE")
            except (ValueError, TypeError, OverflowError):
                reasons.append("OBSERVATION_TIME_UNVERIFIED_OR_STALE")
        raw_score = raw.get("score_ft")
        score = None
        score_state = "ABSENT"
        if raw_score is not None:
            if (isinstance(raw_score,list) and len(raw_score)==2
                    and all(type(v) is int and 0<=v<=30 for v in raw_score)):
                score=tuple(raw_score)
                score_state="PRESENT_UNVERIFIED"
            else:
                score_state="INVALID"
                reasons.append("INVALID_SCORE_OBSERVATION")
        if ko is not None and not start <= ko < end:
            reasons.append("OUTSIDE_WINDOW")
        if status != "SCHEDULED" or ko is None or ko <= now or raw.get("score_ft") is not None:
            reasons.append("NOT_CONFIRMED_FUTURE_PREMATCH")
        # Only identical observations from the same provider/native identity
        # may be deduplicated. Contradictory observations remain visible.
        # Distinguish repeated captures and changed scores. Invalid timestamps or
        # scores are not silently treated as identical valid observations.
        key = (origin, provider, event, league, home, away, ko, status,
               captured, score, score_state, tuple(reasons))
        dedup_eligible = bool(event and provider and ko is not None
                              and score_state!="INVALID"
                              and (raw.get("captured_utc") is None or captured is not None))
        if dedup_eligible and key in seen:
            counts["duplicate_observations"] += 1
            return
        if dedup_eligible:
            seen.add(key)
        link = bool(origin == "public" and event and ko is not None
                    and ko>now and status=="SCHEDULED" and score_state=="ABSENT"
                    and all((league,home,away)) and home!=away
                    and ("core_shadow", event, (league, home, away), ko) in models)
        reasons.extend(["GLOBAL_IDENTITY_NOT_INDEPENDENTLY_ATTESTED",
                        "EXECUTABLE_MARKET_NOT_VERIFIED", "PRODUCTION_GATE_DISABLED"])
        counts["retained_observations"] += 1
        if ko is not None and start <= ko < end:
            counts["in_window_observations"] += 1
        if link:
            counts["exact_core_model_reference_observations"] += 1
        rows.append({"observation_id": hashlib.sha256(json.dumps(
            [counts["input_rows"], origin, provider, event, league, home, away,
             ko.isoformat() if ko else None], ensure_ascii=False).encode()).hexdigest(),
            "origin": origin, "provider": provider, "native_event_id": event,
            "league": league, "home": home, "away": away,
            "kickoff_utc": ko.isoformat() if ko else None,
            "kickoff_hk": ko.astimezone(HK).isoformat() if ko else None,
            "observed_status": status, "exact_core_model_reference": link,
            "captured_utc": captured.isoformat() if captured else None,
            "observed_score_ft_unverified": list(score) if score is not None else None,
            "observed_score_state": score_state,
            "market_1x2": "HOLD", "market_asian_handicap": "HOLD",
            "market_totals": "HOLD", "live_model": "HOLD", "status": "HOLD",
            "reasons": reasons, "production_recommendations": DISABLED})
        if event and provider:
            native_groups[(origin,provider,event)].append(
                (len(rows)-1,(league,home,away,ko,status,score_state,score)))

    def fresh_doc(doc, field):
        try:
            return now - timedelta(hours=10) <= clock(doc[field]) <= now
        except (KeyError, TypeError, ValueError, OverflowError):
            return False

    fixtures = public.get("fixtures") if isinstance(public, dict) else None
    matches = fixtures.get("matches") if isinstance(fixtures, dict) else None
    if isinstance(matches, list):
        sources["public"] = "OBSERVATIONS_ONLY"
        # The public report does not guarantee an independent publication clock.
        for r in matches:
            observe(r, "public")
    else:
        sources["public"] = "UNAVAILABLE"
    if isinstance(worldwide, dict) and worldwide.get("production_recommendations") == DISABLED and isinstance(worldwide.get("leagues"), list):
        sources["worldwide"] = "OBSERVATIONS_ONLY"
        for league in worldwide["leagues"]:
            if not isinstance(league, dict) or not isinstance(league.get("fixture_observations"), list):
                counts["malformed_league_batches"] += 1
                continue
            for r in league["fixture_observations"]:
                observe(r, "worldwide", league.get("id"), fresh_doc(worldwide, "collected_utc"))
    else:
        sources["worldwide"] = "UNAVAILABLE"
    # A native ID reused for differing identity, status or score is retained as
    # conflicting observations, not resolved by ordering or latest capture.
    # Different capture clocks alone do not imply contradictory match facts.
    for group in native_groups.values():
        if len({facts for _,facts in group})>1:
            counts["conflicting_native_id_groups"]+=1
            for index,_ in group:
                row=rows[index]
                row["reasons"].append("NATIVE_ID_OBSERVATION_CONFLICT")
                counts["conflicting_observations"]+=1
                if row["exact_core_model_reference"]:
                    row["exact_core_model_reference"]=False
                    counts["exact_core_model_reference_observations"]-=1
    for field in ("conflicting_native_id_groups","conflicting_observations",
                  "input_rows", "retained_observations", "duplicate_observations",
                  "not_retained_due_to_bound", "in_window_observations",
                  "exact_core_model_reference_observations", "malformed_league_batches"):
        counts.setdefault(field, 0)
    assert counts["input_rows"] == counts["retained_observations"] + counts["duplicate_observations"] + counts["not_retained_due_to_bound"]
    return {"schema": "football-king-global-full-slate-ledger-v1",
            "generated_utc": now.isoformat(), "window_start_hk": start.astimezone(HK).isoformat(),
            "window_end_hk": end.astimezone(HK).isoformat(), "sources": sources,
            "counts": dict(counts), "rows": rows, "status": "HOLD",
            "global_coverage_complete": False, "unique_global_match_count": None,
            "qualified_recommendations": 0, "production_recommendations": DISABLED}

def load(path):
    try:
        path = Path(path)
        if path.stat().st_size > MAX_BYTES:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--worldwide-input", required=True)
    args = parser.parse_args()
    site = Path(args.site)
    now = datetime.now(timezone.utc)
    start = now.astimezone(HK).replace(hour=0, minute=0, second=0, microsecond=0)
    report = build(load(site / "report.json"), load(args.worldwide_input),
                   load(site / "shadow.json"), load(site / "worldwide_shadow.json"),
                   now=now, start=start, end=start + timedelta(days=2))
    (site / "global_full_slate.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "production_recommendations": DISABLED}))

if __name__ == "__main__":
    main()
