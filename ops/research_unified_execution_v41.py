"""One research entry point for a declared V39 batch and selected V4 live links.

The V3 and V35 markets remain distinct; this binds the selected model rates,
fixture, kickoff and clocks, not cross-path quote equality or publisher identity.
Caller-supplied times and labels are untrusted. No production or EV permissions.
"""
from .research_unified_cutoff_v39 import audit_batch, utc, MAX_QUOTE_AGE_SECONDS
from .research_unified_batch_replay_v38 import valid_id
from .research_unified_prematch_replay_v35 import digest
from .research_snapshot_replay_v3 import _decode
from .research_prematch_live_bridge_v4 import link

def run(*, roster, records, cutoff, live_cases=None, live_as_of=None,
        model_release=None, root="."):
    out = {"schema":"unified-execution-v41","status":"HOLD",
           "production_recommendations":"DISABLED","execution_passed":False,
           "source_identity_authenticated":False,"external_timestamp_verified":False,
           "training_admission":False,"qualified_for_production":False,
           "verified_executable_ev":False,"independent_oos_proven":False,
           "cross_path_market_equality_verified":False}
    try:
        batch = audit_batch(roster, records, cutoff=cutoff, root=root)
        if (batch.get("cutoff_verified") is not True or
                batch.get("batch_replay_verified") is not True or
                batch.get("status") != "HOLD" or
                batch.get("production_recommendations") != "DISABLED" or
                any(batch.get(k) is not False for k in (
                    "source_identity_authenticated","external_timestamp_verified",
                    "training_admission","qualified_for_production","verified_executable_ev"))):
            raise ValueError("batch rejected")
        asof = utc(cutoff)
        by_id = {r["event_id"]:r for r in records}
        if live_cases is None:
            live_cases = {}
        if type(live_cases) is not dict or not set(live_cases) <= set(by_id):
            raise ValueError("invalid live subset")
        if live_cases:
            if not valid_id(model_release) or utc(live_as_of) < asof:
                raise ValueError("invalid common live clock or release")
        elif live_as_of is not None or model_release is not None:
            raise ValueError("unexpected live configuration")
        links = {}
        for event, case in sorted(live_cases.items()):
            if type(case) is not dict or set(case) != {"model","inputs"}:
                raise ValueError("invalid link request")
            args = case["inputs"]
            if type(args) is not dict or set(args) != {
                "prematch_raw","prematch_receipt","live_raw_captures",
                "policy","as_of","model_release"}:
                raise ValueError("invalid link input fields")
            if args["model_release"] != model_release or utc(args["as_of"]) != utc(live_as_of):
                raise ValueError("mixed live release or clock")
            r = by_id[event]
            p = _decode(args["prematch_raw"])
            if (p["fixture_id"] != event or utc(p["kickoff"]) != utc(r["kickoff"])
                    or utc(p["as_of"]) != utc(r["frozen_at"])):
                raise ValueError("batch and bridge fixture or clock mismatch")
            chosen = [f for f in r["forecasts"] if f["model"] == case["model"]]
            if len(chosen) != 1:
                raise ValueError("selected forecast missing or ambiguous")
            f = chosen[0]
            if (p["rates"] != [f["home"],f["away"]]
                    or utc(p["rates_at"]) != utc(f["observed"])):
                raise ValueError("selected prior mismatch")
            for snapshot in p["snapshots"]:
                if not 0 <= (asof-utc(snapshot["observed_at"])).total_seconds() <= MAX_QUOTE_AGE_SECONDS:
                    raise ValueError("bridge quote stale at batch cutoff")
            result = link(**args)
            if (result.get("structural_link_passed") is not True
                    or result.get("fixture_id") != event
                    or result.get("status") != "HOLD"
                    or result.get("production_recommendations") != "DISABLED"
                    or result.get("market_evidence") != "ABSENT"
                    or any(result.get(k) is not False for k in (
                        "source_authenticity_verified","independent_oos_proven",
                        "certified_ev","model_promotion_allowed","calibrated"))):
                raise ValueError("live link rejected")
            links[event] = {"model":case["model"],"batch_record_sha256":r["sha256"],
                            "prematch_receipt_sha256":result["prematch_receipt_sha256"],
                            "live_receipt_sha256":result["live_receipt_sha256"],
                            "link_sha256":result["link_sha256"],
                            "score":result["score"],"red_cards":result["red_cards"],
                            "minute":result["minute"],"baseline":result["baseline"],
                            "dynamic":result["dynamic"],"scenario_ranges":result["scenario_ranges"],
                            "comeback_win_scenario":result["comeback_win_scenario"]}
        # All-or-nothing: do not expose partial live results on a failed request.
        result = {**out,"execution_passed":True,"cutoff_utc":asof.isoformat(),
                  "batch_sha256":batch["local_batch_sha256"],
                  "prematch_fixture_count":len(by_id),"live_fixture_count":len(links),
                  "not_requested_live_count":len(by_id)-len(links),
                  "live_as_of_utc":utc(live_as_of).isoformat() if links else None,
                  "model_release":model_release,"live_research":links}
        result["local_execution_sha256"]=digest(result)
        return result
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"reason":"INVALID_OR_INCONSISTENT_EXECUTION_INPUT"}
