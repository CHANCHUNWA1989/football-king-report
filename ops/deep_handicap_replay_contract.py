"""Cross-branch compatibility test with explicitly pinned evaluator checkout."""
import sys
from test_deep_handicap_replay_bridge import fixture, run, FINAL
from deep_handicap_forward_evaluation import evaluate


def main():
    r,m,o=fixture()
    row=run(r,m,o)["evaluation_row"]
    if row is None:
        raise RuntimeError("BRIDGE_REJECTED")
    result=evaluate([row],as_of_utc=FINAL)
    cohort=result["cohorts"]["SYNTHETIC"]["overall"]
    if (cohort["n"]!=1 or cohort["grades"]["FULL_WIN"]!=1 or result["rejected"]
            or result["true_forward_sample_count"]!=0 or result["status"]!="HOLD"
            or result["production_recommendations"]!="DISABLED"
            or result["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]["n"]!=0):
        raise RuntimeError("CROSS_BRANCH_CONTRACT_FAILED")
    duplicate=evaluate([row,row],as_of_utc=FINAL)
    if duplicate["rejected"].get("DUPLICATE_FIXTURE")!=2:
        raise RuntimeError("DUPLICATE_NOT_REJECTED")
    from deep_handicap_batch_isolation import isolate
    from test_deep_handicap_batch_isolation import item
    a,b,c=item(1),item(2),item(3)
    batch=isolate([a,a,b,c],as_of_utc=FINAL)
    merged=evaluate(batch["evaluation_rows"],as_of_utc=FINAL)
    if (batch["accepted_count"]!=2 or batch["rejections"].get("BATCH_COLLISION")!=2
            or merged["cohorts"]["SYNTHETIC"]["overall"]["n"]!=2
            or merged["true_forward_sample_count"]!=0 or merged["rejected"]):
        raise RuntimeError("BATCH_CONTRACT_FAILED")
    print("Synthetic cross-branch contract PASS; true forward samples: 0; HOLD/DISABLED")


if __name__=="__main__":
    main()
