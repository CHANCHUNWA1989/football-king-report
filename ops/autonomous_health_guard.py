"""Fail-closed daily read-only public artifact health monitor.

Uses standard library only. No betting, no model promotion, no repository writes.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ARTIFACTS = ("validation.json", "production_gate.json", "market_status.json")


def inspect_document(name, doc):
    if not isinstance(doc, dict):
        return "INVALID_JSON_OBJECT"
    if name == "validation.json":
        if doc.get("production_recommendations") != "DISABLED":
            return "UNSAFE_PRODUCTION_STATE"
        if not isinstance(doc.get("n"), int) or doc["n"] < 0:
            return "INVALID_SAMPLE_COUNT"
    elif name == "production_gate.json":
        if doc.get("status") != "HOLD":
            return "PRODUCTION_GATE_NOT_HOLD_REQUIRES_MANUAL_REVIEW"
        if doc.get("conditions") and not isinstance(doc["conditions"], dict):
            return "INVALID_GATE_CONDITIONS"
    elif name == "market_status.json":
        if doc.get("production_recommendations") != "DISABLED":
            return "UNSAFE_MARKET_PRODUCTION_STATE"
    return "OK"


def audit(base_url, timeout=10):
    if not base_url.startswith("https://"):
        raise ValueError("HTTPS_REQUIRED")
    result = {
        "schema": "football-king-autonomous-health-v1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "checks": {},
        "automatic_model_changes": False,
        "automatic_betting": False,
    }
    for name in ARTIFACTS:
        try:
            request = Request(base_url.rstrip("/") + "/" + name,
                              headers={"User-Agent": "football-king-health/1.0",
                                       "Accept": "application/json"})
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise ValueError("HTTP_STATUS_" + str(response.status))
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ValueError("DOCUMENT_TOO_LARGE")
                doc = json.loads(raw)
            outcome = inspect_document(name, doc)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError,
                json.JSONDecodeError) as exc:
            outcome = "FETCH_OR_PARSE_ERROR:" + type(exc).__name__
        result["checks"][name] = outcome
    result["status"] = ("PASS" if all(v == "OK" for v in result["checks"].values())
                        else "HOLD")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        report = audit(args.base_url)
    except ValueError as exc:
        report = {"status": "HOLD", "reason": str(exc),
                  "production_recommendations": "DISABLED"}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
