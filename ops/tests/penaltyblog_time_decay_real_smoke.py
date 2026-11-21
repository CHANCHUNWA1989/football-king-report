"""Optional real upstream smoke (requires penaltyblog==1.13.1 in CI)."""
from ops.penaltyblog_time_decay_research import compare
from ops.tests.test_penaltyblog_time_decay_research import fixture


def main():
    for model in ("poisson", "dixon_coles"):
        payload = fixture()
        payload["model"] = model
        result = compare(payload)
        assert result["status"] == "HOLD", result
        assert result["reason"] == "UNVERIFIED_MODEL_COMPARISON_ONLY", result
        assert result["model_promoted"] is False
        assert result["positive_ev_verified"] is False
        assert len(result["unweighted_1x2"]) == len(result["weighted_1x2"]) == 3
        assert abs(sum(result["weighted_1x2"]) - 1) < 1e-6
        print(model, "real dependency weighted fitting succeeded (synthetic data; HOLD)")


if __name__ == "__main__":
    main()
