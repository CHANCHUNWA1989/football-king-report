"""V19 research evidence index. Missing or contradictory stage artifacts fail closed.
Local hashes are not source authentication; release authorization stays disabled.
"""
import math
from ops import v8_multiseason as v

EXTRA_FILES={"market":"v9-market-research.json","schedule":"v9-schedule-venue.json",
             "models":"v9-league-weights.json","history":"v9-history-expansion.json"}

SCHEMAS={"market":"v9-2-market-paired-research-v1",
         "schedule":"v9-4-domestic-schedule-venue-research-v1",
         "models":"v9-5-league-adaptive-ensemble-research-v1",
         "history":"v9-6-expanded-domestic-history-v1"}

def safe(r,schema):
    if type(r) is not dict or r.get("schema")!=schema:raise ValueError("V19_SCHEMA")
    if (r.get("status")!="HOLD" or r.get("production_recommendations")!="DISABLED"
        or type(r.get("verified_forward_sample_credit")) is not int or r["verified_forward_sample_credit"]!=0
        or r.get("automatic_promotion") is not False):raise ValueError("V19_UNSAFE_STAGE")
    return r

def count(x):
    if type(x) is not int or x<0:raise ValueError("V19_COUNT")
    return x

def equal(x,y):
    if count(x)!=count(y):raise ValueError("V19_COUNT_CONFLICT")

def metric(m,n):
    if type(m) is not dict:raise ValueError("V19_METRIC")
    equal(m["n"],n)
    if count(m["correct"])>n:raise ValueError("V19_HITS")
    for key,upper in (("log_loss",100.),("brier",2.)):
        x=m[key]
        if type(x) not in (float,int) or not math.isfinite(x) or not 0<=x<=upper:raise ValueError("V19_METRIC")
    return {k:m[k] for k in ("n","correct","log_loss","brier")}

def stage(r,key,schema,n,n_key="assessment_n"):
    q=safe(r[key],schema);equal(q[n_key],n);return q

def index(reports):
    for k,schema in SCHEMAS.items():safe(reports[k],schema)
    d,u,a,m,h=(reports[k] for k in ("domestic","ucl_archive","ucl_adaptive","models","history"))
    domestic=count(h["historical_domestic_finished"]);ucl=count(u["historical_phase_matches"])
    equal(h["previous_domestic_finished"],d["history_finished"])
    equal(h["new_domestic_finished"],domestic-count(d["history_finished"]))
    equal(h["ucl_historical_finished_reference"],ucl)
    combined=domestic+ucl;equal(h["combined_historical_finished"],combined)
    if h["combined_history_target_30000"] is not (combined>=30000):raise ValueError("V19_HISTORY_FLAG")
    rolling=count(h["rolling_all"]["n"]);latest=count(h["latest_season"]["n"])
    if not 0<latest<=rolling<=domestic:raise ValueError("V19_HISTORY_SCOPE")
    for q,n in ((h["rolling_all"],rolling),(h["latest_season"],latest)):
        for k in ("baseline","candidate"):metric(q[k],n)
    common=count(m["pooled"]["common_n"])
    if not 0<common<=latest:raise ValueError("V19_COMMON_SCOPE")
    equal(m["pooled"]["all_finished"],latest)
    schedule=reports["schedule"];equal(schedule["assessment_n"],latest)
    market=reports["market"];raw_market=count(market["raw_n"]);eligible=count(market["eligible_research_n"])
    if not 0<eligible<=raw_market:raise ValueError("V19_MARKET_SCOPE")
    m14=safe(market["v14_consensus_calibration"],"v14-consensus-calibration-research-v1")
    equal(sum(count(m14[k]) for k in ("development_n","assessment_n","embargo_excluded_n")),eligible)
    st=stage(m,"v10_1_stacking","v10-1-chronological-stacking-research-v1",common)
    ca=stage(m,"v10_causal_experts","v10-causal-eight-expert-research-v1",common)
    by=stage(m,"v11_bayesian_state","v11-dynamic-gamma-poisson-research-v1",common,"common_n")
    moe=stage(m,"v11_3_context_moe","v11-3-context-gated-nine-expert-research-v1",common)
    conf=stage(m,"v17_selective_confidence","v17-domestic-selective-confidence-research-v1",common,"assessment_eligible_n")
    comp=stage(m,"v18_model_competition","v18-causal-model-competition-research-v1",common)
    equal(conf["assessment_all_finished"],latest)
    selected=count(conf["assessment_selected"]["n"])
    if selected>common or (conf["chosen_rule"] is None and selected):raise ValueError("V19_CONFIDENCE_SCOPE")
    if count(conf["assessment_selected"]["correct"])>selected:raise ValueError("V19_CONFIDENCE_HITS")
    equal(comp["pooled"]["n"],common)
    if set(comp["per_league"])!=set(v.LEAGUES):raise ValueError("V19_LEAGUES")
    equal(sum(count(x["n"]) for x in comp["per_league"].values()),common)
    g=stage(a,"dynamic_goal_strength_challenger","ucl-dynamic-country-club-goal-strength-research-v1",144)
    d15=stage(a,"v15_draw_hurdle","v15-ucl-draw-hurdle-research-v1",144)
    d16=stage(d15,"v16_unified_probability","v16-unified-outcome-mass-research-v1",144)
    dom={"v10":metric(ca["pooled"]["same_fixture_metrics"]["candidate"],common),
         "v10_1":metric(st["pooled"]["metrics"]["stack"],common),
         "v11":metric(by["same_fixture_metrics"]["bayes"],common),
         "v11_3":metric(moe["pooled"]["metrics"]["moe"],common),
         "v18_anchor":metric(comp["pooled"]["metrics"]["stack"],common),
         "v18":metric(comp["pooled"]["metrics"]["competition"],common)}
    euro={"goal_strength":metric(g["metrics"]["candidate"],144),
          "v15":metric(d15["metrics"]["candidate"],144),
          "v16":metric(d16["metrics"]["hurdle_reconciled"]["one_x_two"],144)}
    if any(abs(dom["v10_1"][k]-dom["v18_anchor"][k])>1e-9 for k in dom["v10_1"]):raise ValueError("V19_ANCHOR_CONFLICT")
    if any(abs(euro["v15"][k]-euro["v16"][k])>1e-9 for k in euro["v15"]):raise ValueError("V19_SCORE_PROJECTION_CONFLICT")
    return {"schema":"v19-unified-research-evidence-v1","status":"HOLD","production_recommendations":"DISABLED",
        "automatic_promotion":False,"verified_forward_sample_credit":0,
        "historical_archive":{"domestic":domestic,"ucl":ucl,"combined":combined,
            "raw_archive_target_30000":combined>=30000,"rolling_n":rolling,
            "rolling_metrics":h["rolling_all"],"quarantined_scopes":len(h["quarantined_scopes"])},
        "domestic_same_fixture_n":common,"domestic_metrics":dom,"ucl_same_fixture_n":144,"ucl_metrics":euro,
        "market_calibration":m14,"confidence_selection":conf["assessment_selected"],
        "confidence_rule":conf["chosen_rule"],"competition_pooled":comp["pooled"],
        "ucl_score_and_hypothetical_market_metrics":d16["metrics"],
        "feature_status":{"v12_tabpfn":"NO_ACTUAL_INFERENCE_EVIDENCE","v13_xg":"NO_AUTHORIZED_CAPTURE_EVIDENCE",
            "v13_lineup":"NO_AUTHORIZED_CAPTURE_EVIDENCE","live_world_model":"NO_AUTHENTICATED_EVENT_REPLAY"},
        "release_blockers":["INDEPENDENT_FORWARD_0_OF_300","AUTHENTICATED_XG_AND_LINEUPS_MISSING",
            "EXECUTABLE_QUOTE_EVIDENCE_MISSING","INDEPENDENT_REVIEW_AND_RUNTIME_ATTESTATION_MISSING"],
        "historical_metrics_not_independent":True,"same_run_hashes_not_external_attestation":True}
