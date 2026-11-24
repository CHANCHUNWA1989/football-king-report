"""Real installed Penaltyblog v1.13.1 two-model capture, SYNTHETIC data.

Runs only in an isolated research CI job. Does not use historical real
fixtures, live odds, network data or secrets; never uploads a forecast.
"""
from datetime import datetime, timedelta, timezone
from ops.penaltyblog_a_dual_prematch_capture import A_MODEL, SCHEMA, capture
from ops.tests.penaltyblog_real_dependency_smoke import synthetic_payload


def main():
    now = datetime.now(timezone.utc)
    original_fixture = synthetic_payload("poisson")
    target = {
        **original_fixture["target_fixture"],
        "kickoff_utc": (now + timedelta(hours=5)).isoformat(),
    }
    source = {
        **target,
        "produced_utc": (now - timedelta(minutes=2)).isoformat(),
        "max_input_received_utc": (now - timedelta(minutes=3)).isoformat(),
        "model_id": A_MODEL,
        "probabilities": [.5, .3, .2],
        "source_authenticity_verified": False,
        "independently_timestamped": False,
        "production_recommendations": "DISABLED",
    }
    data = {
        "schema": SCHEMA,
        "production_recommendations": "DISABLED",
        "decision_cutoff_utc": (now + timedelta(minutes=3)).isoformat(),
        "original_a": source,
        "historical_matches": original_fixture["historical_matches"],
    }
    report = capture(data)
    assert report["reason"] == "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED", (
        "Real dependency capture BLOCKED; reason=" + report["reason"])
    assert report["status"] == "HOLD"
    assert report["production_recommendations"] == "DISABLED"
    assert report["positive_ev_verified"] is False
    assert report["certified_prospective_samples"] == 0
    assert report["trusted_clock_verified"] is False
    capture_data = report["unverified_triple_capture"]
    assert capture_data["event_id"] == "synthetic_target"
    assert len(capture_data["challenger_observations"]) == 2
    assert [x["model"] for x in capture_data["challenger_observations"]] == [
        "poisson", "dixon_coles"]
    assert all(x["training_match_count"] == 48
               for x in capture_data["challenger_observations"])
    print("REAL penaltyblog 1.13.1: both models fit against synthetic dataset; "
          "one local pre-kickoff handoff produced; trust status HOLD; "
          "no independently witnessed source/time/EV; no public artifact.")


if __name__ == "__main__":
    main()
