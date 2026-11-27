"""Prepare a bounded, outcome-free research input for a dedicated witness run.

The dispatcher's football inputs are untrusted. The runner supplies the forecast
clock; neither the runner clock nor a local receipt is an external time witness.
"""
from datetime import datetime,timezone
import os
from pathlib import Path
from .research_live_intake_v4 import decode
from .research_prospective_fusion_v38 import capture,canonical,exact

MAX_DISPATCH_BYTES=60000

def prepare(submitted,*,runner_clock):
    if not isinstance(submitted,bytes) or not 0<len(submitted)<=MAX_DISPATCH_BYTES:
        raise ValueError("dispatch size")
    doc=decode(submitted)
    exact(doc,"schema event_id league home away kickoff_utc market history")
    if doc["schema"]!="prospective-fusion-dispatch-v44":
        raise ValueError("dispatch schema")
    if runner_clock.tzinfo is None or runner_clock.utcoffset() is None:
        raise ValueError("runner clock required")
    now=runner_clock.astimezone(timezone.utc).isoformat()
    doc.update(schema="prospective-fusion-input-v38",forecast_utc=now)
    raw=canonical(doc)
    receipt=capture(raw,as_of=now)
    if receipt["candidate"]["state"]!="RESEARCH_CANDIDATE":
        raise ValueError("no eligible research prediction")
    return raw,canonical(receipt)

def main():
    if (os.environ.get("GITHUB_REF")!="refs/heads/main"
        or os.environ.get("GITHUB_EVENT_NAME")!="workflow_dispatch"
        or os.environ.get("GITHUB_REPOSITORY")!="CHANCHUNWA1989/football-king-report"
        or os.environ.get("PUBLIC_INPUT_CONFIRMED")!="true"):
        raise ValueError("unauthorized research dispatch context")
    raw,receipt=prepare(os.environ["FUSION_DISPATCH_JSON"].encode("utf-8"),
                        runner_clock=datetime.now(timezone.utc))
    for name,data in (("fusion-input.json",raw),("fusion-receipt.json",receipt)):
        with Path(name).open("xb") as f:f.write(data)

if __name__=="__main__":
    main()
