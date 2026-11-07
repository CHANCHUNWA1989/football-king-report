"""Real optional Penaltyblog fitting smoke test with synthetic fixtures only.

This script never reads real match data, fetches odds, or enables recommendations.
Run only in an isolated environment with penaltyblog installed.
"""
from datetime import datetime, timedelta, timezone
from ops.penaltyblog_research_bridge import SCHEMA, evaluate


def synthetic_payload(model):
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    teams = ["synthetic_a", "synthetic_b", "synthetic_c", "synthetic_d"]
    history = []
    for i in range(48):
        kickoff = base + timedelta(days=i)
        home = teams[i % 4]
        away = teams[(i + 1 + i // 4 % 2) % 4]
        if home == away:
            away = teams[(i + 2) % 4]
        history.append({
            "source_namespace": "synthetic",
            "event_id": f"synthetic_{i}",
            "league_id": "synthetic_league",
            "home_team_id": home,
            "away_team_id": away,
            "kickoff_utc": kickoff.isoformat(),
            "result_recorded_utc": (kickoff + timedelta(hours=3)).isoformat(),
            "home_goals": (i * 7 + 1) % 4,
            "away_goals": (i * 3 + i // 4) % 3,
        })
    return {
        "schema": SCHEMA,
        "production_recommendations": "DISABLED",
        "as_of_utc": (base + timedelta(days=49)).isoformat(),
        "model": model,
        "target_fixture": {
            "source_namespace": "synthetic",
            "event_id": "synthetic_target",
            "league_id": "synthetic_league",
            "home_team_id": "synthetic_a",
            "away_team_id": "synthetic_b",
            "kickoff_utc": (base + timedelta(days=50)).isoformat(),
        },
        "historical_matches": history,
    }


def main():
    for name in ("poisson", "dixon_coles"):
        result = evaluate(synthetic_payload(name))
        assert result["status"] == "RESEARCH_ONLY", (name, result)
        assert result["production_recommendations"] == "DISABLED"
        assert result["positive_ev_verified"] is False
        probs = [result["p_home"], result["p_draw"], result["p_away"]]
        assert all(0 <= p <= 1 for p in probs)
        assert abs(sum(probs) - 1) < 1e-6
        print(f"{name}: real dependency fit OK; synthetic-only; recommendations DISABLED")


if __name__ == "__main__":
    main()
