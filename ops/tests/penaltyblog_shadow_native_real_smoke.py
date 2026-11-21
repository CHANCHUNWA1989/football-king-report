"""Real installed Penaltyblog synthetic smoke via original shadow producer schema.

Only source / teams / outcomes are SYNTHETIC, no live HTTP or market access.
Native IDs and source timestamps are entirely constructed inside this smoke;
this deliberately proves interface compatibility, NOT independent provenance.
"""
from datetime import datetime, timedelta, timezone

from ops.penaltyblog_a_shadow_native_handoff import link
from ops.tests.test_penaltyblog_a_shadow_native_handoff import shadow, z
from ops.tests.penaltyblog_real_dependency_smoke import synthetic_payload


def main():
    now = datetime.now(timezone.utc)
    data = shadow()
    target = data["predictions"][0]
    source = data["sources"][0]
    gen = data["generation_clock"]
    year = now.year if now.month >= 7 else now.year - 1
    data["season"] = f"{year}-{(year+1)%100:02d}"
    source["season"] = data["season"]
    target["native_fixture_input"]["league_season"] = year
    finished = now - timedelta(minutes=2)
    start = now - timedelta(minutes=6)
    observed = now - timedelta(minutes=4)
    cutoff = now + timedelta(minutes=7)
    kickoff = now + timedelta(hours=5)
    data["as_of_utc"] = z(finished)
    target["prediction_utc"] = z(finished)
    target["kickoff_utc"] = z(kickoff)
    gen["started_utc"], gen["completed_utc"] = z(start), z(finished)
    source["captured_utc"] = z(observed)
    # Reuse 48 synthetic games already proven fit-compatible by the upstream
    # dependency smoke. Change only opaque native IDs and provider namespace;
    # no score, match date, or model data is invented from a real source.
    reference = synthetic_payload("poisson")["historical_matches"]
    opaque = {
        "synthetic_a": "101", "synthetic_b": "102",
        "synthetic_c": "103", "synthetic_d": "104",
    }
    mapped_history = []
    for index, fixture in enumerate(reference):
        mapped_history.append({
            **fixture,
            "source_namespace": "openligadb",
            "event_id": f"openligadb:{50000+index}",
            "league_id": "100",
            "home_team_id": opaque[fixture["home_team_id"]],
            "away_team_id": opaque[fixture["away_team_id"]],
        })
    r = link(data, mapped_history, event_id="openligadb:999999",
             cutoff_utc=z(cutoff))
    assert r["status"] == "HOLD"
    assert r["reason"] == "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED", (
        "Blocked real upstream connection: " + r["reason"])
    assert r["production_recommendations"] == "DISABLED"
    assert r["positive_ev_verified"] is False
    assert r["certified_prospective_samples"] == 0
    assert r["shadow_a_native_identity_reused_without_mapping"] is True
    assert r["shadow_source_response_bytes_durably_archived"] is False
    assert r["shadow_source_time_independently_attested"] is False
    assert [a["model"] for a in r["unverified_triple_capture"]["challenger_observations"]] == [
        "poisson", "dixon_coles"]
    assert all(a["training_match_count"] == 48 for a in
               r["unverified_triple_capture"]["challenger_observations"])
    print("REAL installed Penaltyblog: shadow producer schema -> exact native IDs -> "
          "Poisson and Dixon-Coles fits -> locally timed A/2-model HOLD. "
          "SYNTHETIC provider input; no independently authenticated source, "
          "raw provider archive, forecast timestamp or EV.")


if __name__ == "__main__":
    main()
