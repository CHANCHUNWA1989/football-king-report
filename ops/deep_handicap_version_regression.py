"""Cross-version evaluation regression, synthetic fixtures only.

Run old and new evaluators in isolated Python processes with explicit checkout
paths. Existing metrics must be identical after removing only the new field.
This does not certify source provenance or accuracy.
"""
import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from test_deep_handicap_replay_bridge import fixture, run

OLD="ae8c8521aba53d4907421f4d6c4c8b9af485471d"
NEW="078465360bb68c3e26c5dd39d413c2ee763c893c"
AS_OF="2026-06-01T00:00:00Z"
KINDS=("SYNTHETIC","EXTERNAL_UNAUTHENTICATED")
CHILD="""import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root/'ops'))
import deep_handicap_forward_evaluation as e
if Path(e.__file__).resolve()!=root/'ops'/'deep_handicap_forward_evaluation.py':
    raise RuntimeError('WRONG_EVALUATOR_IMPORT')
payload=json.load(sys.stdin)
print(json.dumps(e.evaluate(payload['rows'],as_of_utc=payload['as_of']),allow_nan=False,sort_keys=True))
"""


def require(ok,reason):
    if not ok:
        raise RuntimeError(reason)


def execute(root,sha,rows):
    root=Path(root).resolve()
    actual=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    require(actual==sha,"CHECKOUT_VERSION_MISMATCH")
    raw=subprocess.check_output([sys.executable,"-I","-c",CHILD,str(root)],
          input=json.dumps({"rows":rows,"as_of":AS_OF},allow_nan=False),text=True,timeout=90,
          cwd=root)
    return json.loads(raw)


def samples():
    """Extend a synthetic bridge row into a deterministic time-grid.

    The expanded rows exercise evaluator contracts, not repeated real captures.
    No fixture, timestamps or claimed sources describe actual matches.
    """
    r,m,o=fixture()
    template=run(r,m,o)["evaluation_row"]
    require(template is not None,"SYNTHETIC_BRIDGE_REJECTED")
    rows=[]
    start=datetime(2026,1,5,12,tzinfo=timezone.utc)
    for i in range(120):
        row=copy.deepcopy(template)
        ko=start+timedelta(weeks=i%12,minutes=i)
        cutoff=(ko-timedelta(minutes=30)).isoformat()
        identity={"fixture_id":f"version-test-{i}","home_id":f"home-{i}",
                  "away_id":f"away-{i}","kickoff_utc":ko.isoformat()}
        row.update(**identity,information_cutoff_utc=cutoff)
        for name in ("baseline","challenger"):
            row[name].update(**identity,information_cutoff_utc=cutoff,
                             recorded_utc=(ko-timedelta(minutes=25)).isoformat())
        for obs in row["results"]:
            obs.update(**identity,captured_utc=(ko+timedelta(hours=2)).isoformat(),
                       score_ft=[3,0] if i%2==0 else [2,0])
        rows.append(row)
    return rows


def check_pair(old,new):
    stripped=copy.deepcopy(new)
    require(new["status"]=="HOLD" and new["production_recommendations"]=="DISABLED"
            and new["true_forward_sample_count"]==0
            and new["accuracy_improvement_verified"] is False
            and new["positive_expected_value_verified"] is False,
            "UNSAFE_NEW_EVALUATOR")
    for kind in KINDS:
        diag=stripped["cohorts"][kind].pop("stratified_grade_calibration")
        require(diag["descriptive_only"] is True and diag["source_authenticated"] is False
                and diag["calibration_verified"] is False and diag["recalibration_applied"] is False,
                "UNSAFE_CALIBRATION_DIAGNOSTIC")
    require(stripped==old,"LEGACY_OUTPUT_CHANGED")


def main():
    require(len(sys.argv)==3,"EXPECTED_TWO_CHECKOUTS")
    oldroot,newroot=sys.argv[1:]
    rows=samples()
    variants=[[],rows,rows[:10],rows+[copy.deepcopy(rows[0])]]
    mixed=copy.deepcopy(rows)
    for row in mixed[:60]:
        row["challenger"]["model_id"]="other-synthetic-version"
    variants.append(mixed)
    malformed=copy.deepcopy(rows)
    malformed[0]["results"][0]["score_ft"]=[9,0]
    variants.append(malformed)
    external=copy.deepcopy(rows[:10])
    for i,row in enumerate(external):
        for obj in (row,row["baseline"],row["challenger"],*row["results"]):
            obj["fixture_id"]=f"external-label-test-{i}"
        row["data_kind"]="EXTERNAL_UNAUTHENTICATED"
    variants.append(rows+external)
    for i,batch in enumerate(variants):
        before=execute(oldroot,OLD,batch)
        after=execute(newroot,NEW,batch)
        check_pair(before,after)
        groups=after["cohorts"]["SYNTHETIC"]["stratified_grade_calibration"]["groups"]
        if i==1:
            require(len(groups)==1 and groups[0]["status"]=="DESCRIPTIVE_ONLY"
                    and groups[0]["n"]==120,"FULL_CALIBRATION_MISSING")
            for model in groups[0]["models"].values():
                grade=model["by_grade"]["FULL_WIN"]
                require(abs(grade["observed_fraction"]-.5)<1e-12
                        and abs(grade["signed_gap"]-(grade["mean_forecast"]-.5))<1e-12
                        and model["by_grade"]["PUSH"]["status"]=="STRUCTURALLY_IMPOSSIBLE_FOR_LINE",
                        "CALIBRATION_ARITHMETIC_MISMATCH")
        if i==2 or i==4:
            require(groups and all(g["models"] is None for g in groups),"SPARSE_GROUP_PROMOTED")
        if i==3:
            require(after["rejected"].get("DUPLICATE_FIXTURE")==2,"DUPLICATE_REGRESSION")
        if i==5:
            require(after["rejected"].get("CONFLICTING_RESULT_CLAIMS")==1,"RESULT_CONFLICT_REGRESSION")
        if i==6:
            g=after["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["stratified_grade_calibration"]["groups"]
            require(len(g)==1 and g[0]["n"]==10 and g[0]["models"] is None,"COHORT_ISOLATION_REGRESSION")
    print("Seven synthetic version-regression batches passed; old metrics unchanged; HOLD/DISABLED")


if __name__=="__main__":
    main()
