"""Convert an offline walk-forward model run into strict private pairing input.

The model report is caller supplied. This conversion never authenticates its
source, forecasts or timestamps; it only checks shape and chronology.
"""
import math
from datetime import datetime, timezone


def _time(s):
    if not isinstance(s, str):
        raise ValueError("INVALID_TIME")
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)


def adapt(report, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    if (not isinstance(report, dict) or report.get("status") != "HOLD"
            or report.get("reason") != "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING"
            or report.get("production_recommendations") != "DISABLED"
            or report.get("positive_ev_verified") is not False
            or report.get("independent_provenance_verified") is not False
            or not isinstance(report.get("predictions"), list)
            or not report["predictions"]
            or report.get("refit_count") != len(report["predictions"])):
        raise ValueError("UNTRUSTED_REFIT_REPORT")
    result = []
    seen = set()
    for p in report["predictions"]:
        if not isinstance(p, dict) or set(p) != {
            "fixture_id", "kickoff_utc", "as_of_utc", "model_id",
            "training_match_count", "probabilities",
            "source_authenticity_verified", "independently_timestamped"
        }:
            raise ValueError("INVALID_PREDICTION")
        fixture = p["fixture_id"]
        if not isinstance(fixture, str) or not fixture.strip() or fixture in seen:
            raise ValueError("DUPLICATE_FIXTURE")
        seen.add(fixture)
        if (not isinstance(p["model_id"], str) or
                not p["model_id"].startswith("penaltyblog-") or
                type(p["training_match_count"]) is not int or
                p["training_match_count"] < 30 or
                p["source_authenticity_verified"] is not False or
                p["independently_timestamped"] is not False):
            raise ValueError("UNTRUSTED_FORECAST")
        kickoff, cutoff = _time(p["kickoff_utc"]), _time(p["as_of_utc"])
        if not cutoff < now < kickoff:
            raise ValueError("FORECAST_NOT_PREMATCH")
        probabilities = p["probabilities"]
        if (not isinstance(probabilities, list) or len(probabilities) != 3 or
                any(type(v) not in (int, float) or not math.isfinite(v)
                    or not 0 <= v <= 1 for v in probabilities) or
                abs(sum(probabilities) - 1) > 1e-6):
            raise ValueError("INVALID_PROBABILITIES")
        result.append({"fixture_id": fixture, "kickoff_utc": p["kickoff_utc"],
                       "forecast_utc": p["as_of_utc"],
                       "probabilities": dict(zip(("H", "D", "A"), probabilities)),
                       "model_id": p["model_id"],
                       "source_authenticity_verified": False,
                       "independently_timestamped": False})
    return result
