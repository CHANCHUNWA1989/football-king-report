"""Read-only replay of a fixed archived ledger; no new forward evidence."""
import hashlib
import json
import subprocess
from fourway_calibration_diagnostic import build
from research_strict_json import unique_object,reject_constant
PIN="8f926d2c1aa9739f89975bd561c18239cb0cf28c"
MAX_BYTES=8_000_000
def replay(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES:
        raise ValueError("LEDGER_SIZE")
    if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=PIN:
        raise ValueError("LEDGER_PIN_CHANGED")
    doc=json.loads(raw.decode("utf-8"),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if (not isinstance(doc,dict) or doc.get("production_recommendations")!="DISABLED"
            or not isinstance(doc.get("samples"),list) or type(doc.get("n")) is not int
            or doc["n"]!=len(doc["samples"])):
        raise ValueError("UNSAFE_LEDGER")
    result=build(doc["samples"],checked_utc=doc.get("checked_utc"))
    return {"source_blob":PIN,"archived_checked_utc":doc["checked_utc"],
            "input_count":result["input_count"],"cohort_count":result["cohort_count"],
            "exclusion_reasons":result["exclusion_reasons"],
            "models":{k:{f:v[f] for f in ("n","log_loss","brier")} for k,v in result["models"].items()},
            "descriptive_coverage_met":result.get("descriptive_coverage_met",False),
            "authenticated_forward_samples":0,"production_recommendations":"DISABLED",
            "positive_ev_verified":False,"status":"HOLD"}
if __name__=="__main__":
    raw=subprocess.check_output(["git","cat-file","blob",PIN],timeout=10)
    print(json.dumps(replay(raw),sort_keys=True,allow_nan=False))
