"""Offline V9 scoreboard-to-model bridge. Synthetic scenarios only.

The supplied mapping, red-card scenario, historical envelope and pre-match
rates are not authenticated. No inference of red cards or xG from scores.
This is not a live adapter, source qualification, or betting engine.
"""
import copy
import json
import math
from vnext_offline_intake_e2e import run, scoreboard
from vnext_direct_transport_offline import unique_object, reject_constant
from vnext_integrated_replay import replay


def held(reason, reserved=False):
    return {"status":"HOLD","reason":reason,"production_recommendations":"DISABLED",
            "simulated_reservation":reserved,"source_authenticated":False,
            "source_independence_verified":False,"actual_xg_verified":False,
            "actual_live_odds_verified":False,"positive_ev_verified":False,
            "model_scoring_eligible":False,"real_request_authorized":False,"real_requests":0,
            "synthetic_model_executed":False}


def valid_pmf(p, keys):
    return (type(p) is dict and set(p) == set(keys)
            and all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 1
                    for v in p.values())
            and math.isclose(math.fsum(p.values()),1.0,rel_tol=0,abs_tol=1e-9))


def valid_replay_output(model, fixture):
    if type(model) is not dict or model.get("replay_status") != "RESEARCH_ONLY":
        return False
    if model.get("status") != "HOLD" or model.get("production_recommendations") != "DISABLED":
        return False
    if any(model.get(k) is not False for k in ("source_authenticated",
            "source_independence_verified","model_calibrated","model_scoring_eligible",
            "positive_ev_verified","betting_recommendation_allowed","actual_quote_verified")):
        return False
    if model.get("fixture_id") != fixture or "actual_xg" not in model or model["actual_xg"] is not None:
        return False
    if "model_edge" not in model or model["model_edge"] is not None:
        return False
    if not valid_pmf(model.get("probabilities_1x2"), ("HOME","DRAW","AWAY")):
        return False
    markets = model.get("diagnostic_distributions")
    expected = (("totals","UNDER",2.25),("asian_handicap","HOME",1.25))
    if type(markets) is not list or len(markets) != len(expected):
        return False
    for m, spec in zip(markets,expected):
        if type(m) is not dict or set(m) != {"market","side","line","outcome_probabilities",
                "actual_market_quote_verified","positive_ev_verified"}:
            return False
        if tuple(m.get(k) for k in ("market","side","line")) != spec:
            return False
        if m["actual_market_quote_verified"] is not False or m["positive_ev_verified"] is not False:
            return False
        if not valid_pmf(m["outcome_probabilities"],
                         ("FULL_WIN","HALF_WIN","PUSH","HALF_LOSS","FULL_LOSS")):
            return False
    return True


def simulate(store, *, intake, canonical_fixture, envelope, expected_digest):
    """Run real research replay only after exact synthetic scoreboard binding."""
    reserved = False
    try:
        if type(canonical_fixture) is not str or not canonical_fixture.startswith("synthetic-"):
            return held("SYNTHETIC_FIXTURE_REQUIRED")
        # Snapshot ordinary input containers; not a security boundary against
        # hostile in-process Python objects or concurrent mutation of the store.
        intake, envelope = copy.deepcopy(intake), copy.deepcopy(envelope)
        out = run(store, **intake)
        reserved = out["simulated_reservation"] is True
        if out["stage"] != "COMPLETE" or out["synthetic_scoreboard_agreement"] is not True:
            return held("INTAKE_REJECTED", reserved)
        now = intake["quota"]["now"]
        data = json.loads(intake["transport"]["body"].decode("utf-8"),
                          object_pairs_hook=unique_object, parse_constant=reject_constant)
        pid = intake["mapping"]["primary_id"]
        row = next(r for r in data["response"] if r["fixture"]["id"] == pid)
        phase, minute, home, away = scoreboard(row)
        phase = {"1H":"FIRST_HALF","2H":"SECOND_HALF"}.get(phase)
        if phase is None:
            return held("UNSUPPORTED_MODEL_PHASE", reserved)
        if envelope["decision_epoch"] != now or type(envelope["decision_epoch"]) is not int:
            return held("INTAKE_MODEL_CLOCK_MISMATCH", reserved)
        for key, observed in (("a",intake["primary_observed"]),
                              ("b",intake["secondary"]["observed"])):
            s = envelope[key]
            expected = {"fixture_id":canonical_fixture,"phase":phase,"minute":minute,
                        "home":home,"away":away,"observed":observed}
            if any(type(s[k]) is not type(v) or s[k] != v for k,v in expected.items()):
                return held("INTAKE_MODEL_STATE_MISMATCH", reserved)
        # Red-card fields and prior/history are explicitly supplied synthetic
        # scenario inputs; the scoreboard intake does not verify any of them.
        try:
            model = replay(envelope, expected_digest, now)
            if type(model) is not dict or model.get("replay_status") != "RESEARCH_ONLY":
                return held("MODEL_REJECTED", reserved)
            if not valid_replay_output(model, canonical_fixture):
                return held("MODEL_OUTPUT_QUARANTINED", reserved)
        except Exception:
            # No untrusted exception text or partial forecast is exposed.
            return held("MODEL_EXECUTION_QUARANTINED", reserved)
        result = held("SYNTHETIC_MODEL_REPLAY_ONLY", reserved)
        result.update(synthetic_model_executed=True,
                      synthetic_probabilities_1x2=model["probabilities_1x2"],
                      synthetic_market_distributions=model["diagnostic_distributions"],
                      red_cards_verified=False, actual_xg=None, model_edge=None)
        return result
    except (ValueError,TypeError,KeyError,AttributeError,OSError,OverflowError,
            RecursionError,StopIteration):
        return held("INVALID_BRIDGE_INPUT", reserved)
