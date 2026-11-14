"""Real dependency integration smoke for per-target refits, synthetic only."""
from ops.penaltyblog_walkforward_refit import refit_walkforward
from ops.tests.test_penaltyblog_walkforward_refit import cohort


def main():
    for name in ("poisson", "dixon_coles"):
        data = cohort()
        data["model"] = name
        result = refit_walkforward(data)
        assert result["status"] == "HOLD", result
        assert result["reason"] == "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING", result
        assert result["refit_count"] == 2, result
        assert result["production_recommendations"] == "DISABLED"
        assert result["positive_ev_verified"] is False
        assert result["independent_provenance_verified"] is False
        for forecast in result["predictions"]:
            assert len(forecast["probabilities"]) == 3
            assert abs(sum(forecast["probabilities"]) - 1) < 1e-6
        print(f"{name}: two actual dependency refits passed, synthetic-only, HOLD")


if __name__ == "__main__":
    main()
