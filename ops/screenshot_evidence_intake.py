"""Fail-closed screenshot evidence intake, no OCR or fabricated identity.

Consumes a human-reviewed screenshot manifest, validates content SHA256,
point-in-time capture, score and fixture identity, and emits a research-only
case for the existing provider pipeline. No image extraction is claimed.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime,timezone
from pathlib import Path
from live_market_research import utc

SCHEMA="football-king-screenshot-evidence-v1"
MAX_IMAGE_BYTES=15_000_000
ALLOWED={".png",".jpg",".jpeg",".webp"}

def intake(image_bytes, manifest, *, now=None):
    if not isinstance(image_bytes,bytes) or not 0<len(image_bytes)<=MAX_IMAGE_BYTES:
        raise ValueError("INVALID_IMAGE_SIZE")
    if not isinstance(manifest,dict):
        raise ValueError("INVALID_MANIFEST")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    blockers=[]
    digest=hashlib.sha256(image_bytes).hexdigest()
    if manifest.get("image_sha256")!=digest:
        blockers.append("IMAGE_HASH_MISMATCH")
    fixture=manifest.get("fixture")
    fixture=fixture if isinstance(fixture,dict) else {}
    required=("event_id","league","home","away")
    if not all(isinstance(fixture.get(k),str) and fixture[k].strip() for k in required):
        blockers.append("MISSING_FIXTURE_IDENTITY")
    elif fixture["home"].strip().casefold()==fixture["away"].strip().casefold():
        blockers.append("DUPLICATE_TEAMS")
    screenshot=manifest.get("screenshot")
    screenshot=screenshot if isinstance(screenshot,dict) else {}
    if screenshot.get("event_id")!=fixture.get("event_id"):
        blockers.append("SCREENSHOT_EVENT_MISMATCH")
    if screenshot.get("human_reviewed") is not True:
        blockers.append("SCREENSHOT_NOT_HUMAN_REVIEWED")
    try:
        ts=utc(screenshot.get("observed_at_utc"))
        age=(now-ts).total_seconds()
        if not -10<=age<=120:
            blockers.append("SCREENSHOT_STALE_OR_FUTURE")
    except (TypeError,ValueError,OverflowError):
        blockers.append("INVALID_SCREENSHOT_TIMESTAMP")
    for k in ("home_goals","away_goals"):
        v=screenshot.get(k)
        if type(v) is not int or not 0<=v<=25:
            blockers.append("INVALID_"+k.upper())
    minute=screenshot.get("minute")
    if type(minute) not in (int,float) or not math.isfinite(minute) or not 0<=minute<=125:
        blockers.append("INVALID_MATCH_MINUTE")
    if screenshot.get("ocr_confidence") is not None:
        # Never allow a caller-provided confidence number to masquerade
        # as a verified OCR result from an actual model.
        blockers.append("UNVERIFIED_OCR_CONFIDENCE")
    safe_fixture={k:fixture.get(k) for k in required}
    safe_fixture["independent_fixture_sources"]=0
    safe_screenshot={k:screenshot.get(k) for k in (
        "event_id","observed_at_utc","home_goals","away_goals","minute")}
    return {"schema":SCHEMA,"status":"RESEARCH_ONLY" if not blockers else "HOLD",
            "image_sha256":digest,"human_reviewed_claim":screenshot.get("human_reviewed") is True,
            "blockers":blockers,
            "case":{"fixture":safe_fixture,"screenshot":safe_screenshot},
            "fixture_independently_verified":False,
            "ocr_performed":False,"can_publish_pick":False,
            "recommendation":None,"production_recommendations":"DISABLED"}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--image",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--output",default="screenshot-evidence-audit.json")
    a=p.parse_args(argv)
    path=Path(a.image)
    if path.suffix.lower() not in ALLOWED:
        raise ValueError("UNSUPPORTED_IMAGE_FORMAT")
    if path.stat().st_size>MAX_IMAGE_BYTES:
        raise ValueError("INVALID_IMAGE_SIZE")
    result=intake(path.read_bytes(),json.loads(Path(a.manifest).read_text(encoding="utf-8")))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"blockers":result["blockers"],
                      "ocr_performed":False},ensure_ascii=False))

if __name__=="__main__":
    main()
