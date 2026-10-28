"""Private ephemeral odds collector for the all-market screener.

Raw quotes stay in the ephemeral Actions workspace, never in public artifacts,
commits or GitHub Pages. No inferred model probabilities or source certification.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from ops.odds_market import retrieve, verify, may_spend, APIProblem, SPORTS
from ops.private_h2h_evidence import FEED_SCHEMA, bind_response

def collect(key, now=None, *, capture=None):
    # An explicit clock is a fixed offline/replay cutoff. Production must
    # timestamp each response after retrieval, not before a slow API batch.
    if now is not None:
        if capture is not None:
            raise ValueError("OFFLINE_CLOCK_CANNOT_CAPTURE_RESPONSE")
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("INVALID_COLLECTION_CLOCK")
        now = now.astimezone(timezone.utc)
    options = {"capture": capture} if capture is not None else {}
    catalog = verify(key, **options)
    quota = catalog["quota"]
    rows, coverage = [], []
    attempted, first_error, quota_blocked = False, None, False
    for league, sport in SPORTS.items():
        if not catalog["supported"].get(league) or not catalog["active"].get(league):
            coverage.append({"league": league, "reason": "NOT_AVAILABLE"})
            continue
        if not may_spend(quota):
            coverage.append({"league": league, "reason": "QUOTA_GUARD"})
            quota_blocked = True
            break
        try:
            events, quota = retrieve("/sports/"+sport+"/odds/", key, params={
                "regions": "eu", "markets": "h2h",
                "oddsFormat": "decimal", "dateFormat": "iso"}, **options)
        except APIProblem as e:
            first_error = first_error or str(e)
            coverage.append({"league": league, "reason": str(e)})
            if str(e) in ("RATE_LIMITED", "KEY_REJECTED_OR_NOT_AUTHORIZED", "SPORT_OR_PLAN_NOT_AUTHORIZED",
                          "PRIVATE_RESPONSE_CAPTURE_REJECTED"):
                break
            continue
        if not isinstance(events, list) or quota.get("remaining") is None:
            coverage.append({"league": league, "reason": "BAD_RESPONSE_OR_QUOTA"})
            break
        captured = (datetime.fromisoformat(capture.last_receipt["completed_utc"])
                    if capture is not None else now if now is not None else datetime.now(timezone.utc))
        attempted = True
        # Reuse this exact completed response: no new request or market spend.
        bound = bind_response(events, league=league, sport=sport, captured=captured)
        rows.extend(bound["quotes"])
        coverage.append({"league": league, "quotes": len(bound["quotes"]),
                         "content_rejections": bound["rejected"]})
    status = ("CONNECTED" if attempted else "QUOTA_GUARD" if quota_blocked
              else "PROVIDER_ERROR" if first_error else "NO_ACTIVE_LEAGUES")
    return {"schema": FEED_SCHEMA, "quotes": rows, "coverage": coverage, "source": "The Odds API private research",
            "collector_status": status, "collector_reason": first_error,
            "production_recommendations": "DISABLED", "requested_markets": ["h2h"],
            "other_markets_status": "NOT_REQUESTED_FREE_QUOTA_GUARD"}


def replay_private_quotes(root, feed, *, source_sha, run_id, attempt, expected_manifest_sha256):
    """Rebuild this run's normalized rows from captured bytes, never certify them."""
    from ops.private_response_capture import replay_records
    if (not isinstance(feed, dict) or feed.get("schema") != FEED_SCHEMA
            or not isinstance(feed.get("quotes"), list)
            or feed.get("production_recommendations") != "DISABLED"):
        raise ValueError("INVALID_PRIVATE_REPLAY_FEED")
    records = replay_records(root, source_sha=source_sha, run_id=run_id, attempt=attempt,
                             expected_manifest_sha256=expected_manifest_sha256)
    rows, odds_responses = [], 0
    for record in records:
        receipt = record["receipt"]
        if receipt["endpoint_path"] == "/sports/":
            continue
        sport = receipt["endpoint_path"].split("/")[2]
        league = next(code for code, value in SPORTS.items() if value == sport)
        captured = datetime.fromisoformat(receipt["completed_utc"])
        bound = bind_response(json.loads(record["raw"]), league=league, sport=sport, captured=captured)
        rows.extend(bound["quotes"])
        odds_responses += 1
    try:
        # JSON canonicalization preserves bool/int/float distinctions that == loses.
        expected = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False)
        observed = json.dumps(feed["quotes"], sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("PRIVATE_CAPTURE_QUOTE_REPLAY_MISMATCH") from None
    if expected != observed:
        raise ValueError("PRIVATE_CAPTURE_QUOTE_REPLAY_MISMATCH")
    return {"schema": "football-king-private-response-quote-replay-v1",
            "replay_completed": True, "captured_response_count": len(records),
            "odds_response_count": odds_responses, "replayed_quote_count": len(rows),
            "raw_source_authenticated": False, "durable_handoff_completed": False,
            "certified_case_count": 0, "status": "HOLD", "production_recommendations": "DISABLED"}

def main():
    key = os.environ.get("THE_ODDS_API_KEY", "")
    capture = None
    if not key:
        result = {"schema": FEED_SCHEMA, "quotes": [], "coverage": [], "collector_status": "MISSING_API_KEY",
                  "collector_reason": "THE_ODDS_API_KEY_NOT_CONFIGURED",
                  "production_recommendations": "DISABLED"}
    else:
        try:
            capture_dir = os.environ.get("PRIVATE_RESPONSE_CAPTURE_DIR")
            if capture_dir:
                from ops.private_response_capture import CaptureSession
                capture = CaptureSession(Path(capture_dir), source_sha=os.environ.get("GITHUB_SHA", ""),
                                         run_id=os.environ.get("GITHUB_RUN_ID", ""),
                                         attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
            result = collect(key, **({"capture": capture} if capture is not None else {}))
        except (APIProblem, ValueError, TypeError, OSError) as e:
            # Never serialize provider exceptions, URLs, credentials or response bodies.
            result = {"schema": FEED_SCHEMA, "quotes": [], "coverage": [], "collector_status": "PROVIDER_ERROR",
                      "collector_reason": "COLLECTOR_EXCEPTION_" + type(e).__name__,
                      "production_recommendations": "DISABLED"}
    if capture is not None:
        try:
            sealed = capture.seal()
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with open(output, "a", encoding="utf-8") as stream:
                    stream.write("private_capture_manifest_sha256=" + sealed["manifest_sha256"] + "\n")
        except (ValueError, TypeError, OSError):
            result = {"schema": FEED_SCHEMA, "quotes": [], "coverage": [],
                      "collector_status": "PROVIDER_ERROR",
                      "collector_reason": "PRIVATE_CAPTURE_FINALIZATION_FAILED",
                      "production_recommendations": "DISABLED"}
        finally:
            capture.close()
    target = Path("output/private_all_market_quotes.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print("COLLECTOR_STATUS:", result["collector_status"], "QUOTES:", len(result["quotes"]))

if __name__ == "__main__":
    main()
