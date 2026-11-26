"""V33 unified current research acceptance: bind actual same-run evidence.
No production promotion, external source attestation, or simulated sample credit.
"""
import argparse,json,math
from pathlib import Path
from ops.v19_evidence_index import safe,metric,count,equal
from ops.v6_forward_bundle import decode
from ops.v27_stack_archive import audit,sha
from ops.v29_xg_residual import checked
from ops.v8_multiseason import LEAGUES
def build(root):
    p=Path(root);hashes={}
    def read(name):
        f=p/name
        if not 0<f.stat().st_size<=8_000_000:raise ValueError("EVIDENCE_SIZE")
        raw=f.read_bytes();hashes[name]=sha(raw);return raw
    def get(name):return decode(read(name))
    m=safe(get("v9-league-weights.json"),"v9-5-league-adaptive-ensemble-research-v1")
    n=count(m["pooled"]["common_n"]);out={}
    anchor=metric(m["v10_1_stacking"]["pooled"]["metrics"]["stack"],n)
    for k,schema,key in (("v26_nonlinear_meta","v26-nonlinear-meta-research-v1","challenger"),
                         ("v28_joint_fusion","v28-joint-fusion-research-v1","fusion"),
                         ("v31_context_residual","v31-context-residual-research-v1","candidate")):
        q=safe(m[k],schema);equal(q["assessment_n"],n)
        a=metric(q["pooled"]["metrics"]["stack"],n)
        if any(abs(a[t]-anchor[t])>1e-9 for t in anchor):raise ValueError("ANCHOR_CONFLICT")
        candidate=metric(q["pooled"]["metrics"][key],n)
        if set(q["per_league"])!=set(LEAGUES):raise ValueError("LEAGUE_SCOPE")
        equal(sum(count(x["n"]) for x in q["per_league"].values()),n)
        out[k]={"metrics":candidate,"historical_gate":q["pooled"]["historical_proper_score_gate"]}
    ex=m["v29_anchor_export"];raw=read("v29-stack-reference.json");ref=checked(raw,ex["sha256"])
    equal(len(raw),ex["bytes"]);equal(sum(r["season"]=="2025-26" for r in ref["rows"]),n)
    f=get("v27-archive-diagnostic.json");ledger=safe(get("v32-stack-ledger-report.json"),"v32-same-cut-ledger-research-v1")
    if f.get("status")!="HOLD" or f.get("production_recommendations")!="DISABLED" or f.get("verified_forward_sample_credit")!=0:raise ValueError("ARCHIVE_FLAGS")
    sealed=count(f["sealed_count"]);equal(ledger["unique_fixture_count"],sealed);equal(ledger["pending_count"],sealed);equal(ledger["settled_count"],0)
    if sealed:
        equal(f["raw_replay_n"],sealed)
        a=audit(read("v27-stack-archive.zip"),f["archive_sha256"]);equal(len(a["rows"]),sealed)
    elif (p/"v27-stack-archive.zip").exists():raise ValueError("UNEXPECTED_ARCHIVE")
    return {"schema":"v33-unified-batch-research-v1","assessment_n":n,"reference_model":"V10.1","reference_metrics":anchor,
        "challengers":out,"real_shadow_sealed":sealed,"unique_local_research_fixtures":sealed,
        "historical_anchor_rows":len(ref["rows"]),"artifact_sha256":hashes,
        "actual_xg":"NOT_CONNECTED","actual_player_lineup":"NOT_CONNECTED","actual_tactics":"NOT_CONNECTED",
        "tabpfn":"NO_ACTUAL_INFERENCE_EVIDENCE","market_live":"NOT_CONNECTED","permanent_external_store":"NOT_PROVISIONED",
        "independent_forward_target":300,"verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    d=build(a.input_dir)
    with Path(a.output).open("x") as f:json.dump(d,f,indent=2,allow_nan=False)
    print(json.dumps(d,allow_nan=False))
if __name__=="__main__":main()
