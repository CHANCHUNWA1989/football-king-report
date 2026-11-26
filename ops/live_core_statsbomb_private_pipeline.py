"""Ephemeral, opt-in historical replay acceptance. No publication or promotion."""
import argparse
import json
import tempfile
from pathlib import Path

from live_core_statsbomb_acquire import acquire
from live_core_statsbomb_cohort import run


def execute(temp_parent, *, rights_confirmed=False):
    if rights_confirmed is not True:
        raise ValueError("OPERATOR_RIGHTS_CONFIRMATION_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="football-private-replay-",dir=temp_parent) as d:
        root=Path(d)/"cohort"
        try:
            acquired=acquire(root,rights_confirmed=True)
            if (type(acquired.get("downloaded")) is not int
                    or acquired["downloaded"]!=64
                    or acquired.get("index_verified") is not True
                    or acquired.get("byte_identity_verified") is not True):
                raise ValueError("ACQUISITION_INCOMPLETE")
        except Exception:
            raise ValueError("PRIVATE_ACQUISITION_FAILED") from None
        try:
            report=run(root)
            if (type(report.get("scheduled")) is not int or report["scheduled"]!=64
                    or type(report.get("accepted")) is not int or report["accepted"]!=64
                    or report.get("complete_cohort") is not True
                    or report.get("rejected_match_ids")!=[]):
                raise ValueError("INCOMPLETE")
        except Exception:
            raise ValueError("PRIVATE_REPLAY_INCOMPLETE") from None
    return {"status":"PRIVATE_REPLAY_FINISHED","production_recommendations":"DISABLED",
            "model_calibrated":False,"verified_forward_sample_credit":0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("temp_parent",type=Path)
    p.add_argument("--confirm-research-rights",action="store_true")
    args=p.parse_args()
    try:
        report=execute(args.temp_parent,rights_confirmed=args.confirm_research_rights)
    except Exception:
        # Do not disclose provider payloads, fixture IDs or exception details in CI.
        print("PRIVATE_REPLAY_NOT_COMPLETED")
        return 1
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
