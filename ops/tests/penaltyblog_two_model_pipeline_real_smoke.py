"""Actual penaltyblog two-model pipeline smoke on synthetic fixtures only."""
from ops.penaltyblog_two_model_pipeline import run_pipeline
from ops.tests.test_penaltyblog_two_model_pipeline import fixture


def main():
    result = run_pipeline(fixture())
    assert result["status"] == "HOLD", result
    assert result["reason"] == "UNVERIFIED_SOURCE_AND_PROSPECTIVE_ATTESTATION", result
    assert result["paired_fixture_count"] == 2, result
    assert result["model_refit_counts"] == {"poisson": 2, "dixon_coles": 2}
    for name in ("poisson", "dixon_coles"):
        assert result["unverified_diagnostic_metrics"][name]["sample_count"] == 2
    assert result["production_recommendations"] == "DISABLED"
    assert result["positive_ev_verified"] is False
    print("Real optional dependency: 4 refits, paired scoring, synthetic-only, HOLD")


if __name__ == "__main__":
    main()
