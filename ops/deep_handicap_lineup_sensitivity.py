"""Research-only lineup-change sensitivity using stable claimed player IDs.

No player valuation, injury authentication, actual starting-XI verification,
source fetching, or adjustment of existing forecasts. A changed player need
not weaken a team; the profiles deliberately include upside and downside.
"""
import math
import re
from datetime import timedelta
from lineup_guard import audit, _utc
from asian_handicap_research import _poisson, quarter_units
from deep_handicap_joint_score import project, _total_units

SCHEMA = "football-king-dhe-lineup-sensitivity-v1"
PROFILES = ((.96, 1.02), (1.0, 1.0), (1.02, .99))
ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


def _ids(value):
    if (type(value) is not list or len(value) != 11
            or any(type(v) is not str or not ID.fullmatch(v) for v in value)
            or len(set(value)) != 11):
        raise ValueError("INVALID_PLAYER_IDS")
    return set(value)


def _roster(record, fixture, namespace):
    if (type(record) is not dict or record.get("fixture") != fixture
            or record.get("player_id_namespace") != namespace):
        raise ValueError("FIXTURE_OR_NAMESPACE_MISMATCH")
    h, a = _ids(record.get("home_starters")), _ids(record.get("away_starters"))
    if h & a:
        raise ValueError("CROSS_TEAM_PLAYER_ID")
    return h, a


def analyze(forecast, reference, lineup, *, as_of_utc, home_rate, away_rate,
            side, handicap, total_line):
    """Compare a prior declared XI with a later declared official XI.

    Both are unverified claims in the same player ID namespace. The earlier
    XI is a predeclared comparison roster, not proof of the players assumed
    by the goal-rate model. Scenario multipliers are not fitted.
    """
    out = {"schema": SCHEMA, "status": "HOLD",
           "production_recommendations": "DISABLED", "research_only": True,
           "qualifies_for_betting": False, "positive_expected_value_verified": False,
           "official_lineup_authenticated": False, "injury_status_authenticated": False,
           "player_value_model_calibrated": False, "baseline_roster_model_binding_verified": False,
           "forecast_modified": False, "scenarios": [], "reason": "INVALID_INPUT"}
    try:
        _poisson(home_rate)
        _poisson(away_rate)
        if quarter_units(handicap) > -6 or side not in ("HOME", "AWAY"):
            raise ValueError("BAD_MARKET")
        _total_units(total_line)
        now, prediction, ko = _utc(as_of_utc), _utc(forecast["prediction_utc"]), _utc(forecast["kickoff_utc"])
        if not prediction == now or now >= ko - timedelta(minutes=10):
            raise ValueError("NOT_CURRENT_PREMATCH_PREDICTION")
        if forecast.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_FORECAST")
        if any(forecast.get(k) is not None for k in ("result", "score_ft", "historical_outcome", "y")):
            raise ValueError("RESULT_BEARING_FORECAST")
        fixture = {k: forecast[k] for k in ("league", "home", "away", "event_id", "kickoff_utc")}
        if any(type(fixture[k]) is not str or not fixture[k].strip() for k in fixture):
            raise ValueError("BAD_FIXTURE")
        if fixture["home"] == fixture["away"]:
            raise ValueError("BAD_FIXTURE")
        namespace = reference.get("player_id_namespace")
        if type(namespace) is not str or not ID.fullmatch(namespace):
            raise ValueError("INVALID_NAMESPACE")
        rh, ra = _roster(reference, fixture, namespace)
        lh, la = _roster(lineup, fixture, namespace)
        if reference.get("kind") != "PREDECLARED_REFERENCE_XI":
            raise ValueError("MISSING_REFERENCE_XI")
        if lineup.get("kind") != "OFFICIAL_STARTING_XI_CLAIM":
            raise ValueError("NOT_OFFICIAL_XI_CLAIM")
        if (rh | lh) & (ra | la):
            raise ValueError("PLAYER_SWITCHED_TEAMS")
        recorded = _utc(reference["recorded_utc"])
        published, captured = _utc(lineup["published_utc"]), _utc(lineup["captured_utc"])
        if not recorded < published <= captured <= prediction < ko:
            raise ValueError("LINEUP_TIME_ORDER")
        if not timedelta(0) <= prediction-recorded <= timedelta(days=7):
            raise ValueError("STALE_REFERENCE_XI")
        # Adapt stable IDs to the existing structural XI and chronology audit.
        # This deliberately does not upgrade any authentication flags.
        evidence = {k: lineup[k] for k in ("fixture", "published_utc", "captured_utc",
                    "home_starters", "away_starters", "source_url")}
        guard = audit({**forecast, "lineup_evidence": evidence})
        if guard["status"] != "STRUCTURAL_RESEARCH_ONLY":
            raise ValueError("LINEUP_GUARD_REJECTED")
        nh, na = len(rh-lh), len(ra-la)
        pending = []
        for hprofile in PROFILES:
            for aprofile in PROFILES:
                h = home_rate*hprofile[0]**nh*aprofile[1]**na
                a = away_rate*aprofile[0]**na*hprofile[1]**nh
                # Do not clip away extreme scenarios or publish partial ranges.
                _poisson(h)
                _poisson(a)
                p = project(h,a,side,handicap,total_line)
                p.update(schema=SCHEMA, model_assumption="UNFITTED_LINEUP_CHANGE_SENSITIVITY",
                         home_profile=list(hprofile),away_profile=list(aprofile),
                         hypothetical_home_rate=h,hypothetical_away_rate=a)
                pending.append(p)
        values = [p["handicap"]["FULL_WIN"] for p in pending]
        out.update(reason="STRUCTURALLY_VALID_LINEUP_CLAIMS_SENSITIVITY_ONLY",
                   home_changes=nh,away_changes=na,scenarios=pending,scenario_count=len(pending),
                   full_win_envelope={"min":min(values),"max":max(values)},
                   reference_is_not_verified_model_training_lineup=True,
                   changed_players_are_not_verified_injuries=True)
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
        allowed = {"BAD_MARKET","NOT_CURRENT_PREMATCH_PREDICTION","UNSAFE_FORECAST",
                   "RESULT_BEARING_FORECAST","BAD_FIXTURE","INVALID_NAMESPACE",
                   "FIXTURE_OR_NAMESPACE_MISMATCH","INVALID_PLAYER_IDS","CROSS_TEAM_PLAYER_ID",
                   "MISSING_REFERENCE_XI","NOT_OFFICIAL_XI_CLAIM","PLAYER_SWITCHED_TEAMS",
                   "LINEUP_TIME_ORDER","STALE_REFERENCE_XI","LINEUP_GUARD_REJECTED",
                   "INVALID_EXPECTED_GOALS"}
        out["reason"] = str(exc) if str(exc) in allowed else "INVALID_INPUT"
    return out
