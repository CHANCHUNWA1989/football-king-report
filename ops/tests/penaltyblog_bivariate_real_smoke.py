"""Upstream Penaltyblog 1.13.1 real-math smoke, synthetic observations only."""
from datetime import datetime, timedelta, timezone

from ops.penaltyblog_bivariate_goals_challenger import SCHEMA, compare


def synthetic_payload():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    teams = ("a", "b", "c", "d", "e", "f")
    rows = []
    for i in range(96):
        home = teams[i % 6]
        away = teams[(i % 6 + 1 + (i // 6) % 5) % 6]
        kickoff = start + timedelta(days=i)
        rows.append({
            "source_namespace": "synthetic", "event_id": f"history-{i}",
            "league_id": "synthetic", "home_team_id": home, "away_team_id": away,
            "kickoff_utc": kickoff.isoformat(),
            "result_recorded_utc": (kickoff + timedelta(hours=3)).isoformat(),
            "home_goals": (i + i // 7) % 4,
            "away_goals": (i // 2 + i // 5) % 4,
        })
    kickoff = start + timedelta(days=100)
    return {
        "schema": SCHEMA, "production_recommendations": "DISABLED",
        "model": "bivariate_poisson",
        "as_of_utc": (kickoff - timedelta(hours=2)).isoformat(),
        "target_fixture": {
            "source_namespace": "synthetic", "event_id": "upcoming",
            "league_id": "synthetic", "home_team_id": "a", "away_team_id": "b",
            "kickoff_utc": kickoff.isoformat(),
        },
        "historical_matches": rows,
    }


def main():
    result = compare(synthetic_payload())
    assert result["reason"] == "UNVERIFIED_BIVARIATE_RESEARCH_ONLY", result
    assert result["status"] == "HOLD"
    assert result["production_recommendations"] == "DISABLED"
    assert result["model_promoted"] is False
    assert result["positive_ev_verified"] is False
    assert result["training_match_count"] == 96
    for name in ("unweighted", "time_weighted"):
        markets = result["models"][name]
        assert abs(sum(markets["probabilities_1x2_home_draw_away"]) - 1) < 1e-8
        for category in ("over_total_goals_settlement", "home_asian_handicap_settlement"):
            for line, buckets in markets[category].items():
                assert abs(sum(buckets.values()) - 1) < 1e-8, (name, category, line)
        assert markets["over_total_goals_settlement"]["2.75"]["half_win"] > 0
    print("Bivariate Poisson real upstream fit succeeded on synthetic observations; HOLD")


if __name__ == "__main__":
    main()
