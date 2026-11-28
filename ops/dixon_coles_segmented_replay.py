"""Experimental segmented verification on supplied proof manifests only.

Use the original verifier on every segment, then union claim indexes before
any case selection or scoring. Never certify source truth, skip failures,
or claim a complete remote history. No workflow calls this module.
"""
from ops import dixon_coles_forward_replay as replay

SEGMENT_SIZE = 16
MAX_TOTAL_CAPTURES = 256
MAX_TOTAL_BYTES = replay.MAX_CAPTURE_PAYLOAD_BYTES


def _key(options):
    return options["run_id"], options["attempt"]


def _reference_key(ref):
    return ref["run_id"], ref["run_attempt"]


def _read_segments(entries, current, snapshots, needed, metadata):
    # Freeze every proof's identity and bytes before any capture verification.
    prepared, seen = [], set()
    total = 0
    for entry in entries:
        folder, options = replay._entry(entry, forecast=False)
        key = _key(options)
        replay._require(key not in seen,"DUPLICATE_CAPTURE_RUN_ATTEMPT")
        seen.add(key)
        before={}
        for name, maximum in replay.CAPTURE_FILES.items():
            payload = replay.capture_provenance._read(folder/name,maximum)
            total += len(payload)
            replay._require(total <= MAX_TOTAL_BYTES,"CAPTURE_HISTORY_PAYLOAD_LIMIT")
            before[name]=replay._digest(payload)
        del payload
        prepared.append((folder,options,before))
    catalogue = [[options,before] for _,options,before in prepared]
    digest = replay._digest(replay.producer._canonical(catalogue))
    merged = {key:{"identities":set(),"scores":set(),"invalid":False,"finals":[]}
              for key in needed}
    references=[]
    segment_count=0
    for start in range(0,len(prepared),SEGMENT_SIZE):
        chunk=prepared[start:start+SEGMENT_SIZE]
        for folder,_,before in chunk:
            replay._require(replay._snapshot(folder,replay.CAPTURE_FILES)==before,
                            "CAPTURE_BYTES_CHANGED_BEFORE_SEGMENT")
        local_snapshots=[]
        part, refs=replay._results(entries[start:start+len(chunk)],current,
                                  local_snapshots,needed)
        expected=[_key(options) for _,options,_ in chunk]
        replay._require([_reference_key(r) for r in refs]==expected
                        and len(local_snapshots)==len(chunk)
                        and set(part)==set(merged),"SEGMENT_COVERAGE_MISMATCH")
        for (folder, options, before),ref,(verified_folder,files,verified_before) in zip(chunk,refs,local_snapshots):
            replay._require(folder==verified_folder and files==replay.CAPTURE_FILES
                            and before==verified_before
                            and ref["source_commit"]==options["source_sha"]
                            and ref["workflow_commit"]==options["workflow_sha"]
                            and ref["subject_sha256"]=={replay.capture_provenance.SUBJECT_NAME:before[replay.capture_provenance.SUBJECT_NAME]}
                            and ref["bundle_sha256"]==before[replay.capture_provenance.BUNDLE_NAME],
                            "SEGMENT_PROOF_BINDING_MISMATCH")
        # Do not choose a winner locally: retain conflicts across every batch.
        for key,bucket in part.items():
            target=merged[key]
            target["identities"].update(bucket["identities"])
            target["scores"].update(bucket["scores"])
            target["invalid"] = target["invalid"] or bucket["invalid"]
            target["finals"].extend(bucket["finals"])
        references.extend(refs)
        snapshots.extend(local_snapshots)
        segment_count+=1
    replay._require(len(references)==len(prepared),"SEGMENT_COVERAGE_MISMATCH")
    metadata.update(segment_count=segment_count,verified_capture_count=len(references),
                    supplied_catalogue_sha256=digest,decoded_capture_bytes=total)
    return merged,references


def audit(forecasts,captures,*,now=None):
    """In-process research adapter; no new trusted inputs or production switch."""
    metadata={}
    def reader(entries,current,snapshots,needed):
        return _read_segments(entries,current,snapshots,needed,metadata)
    report=replay._audit(forecasts,captures,now=now,result_reader=reader,
                         capture_limit=MAX_TOTAL_CAPTURES)
    details=dict(segmented_replay_experimental=True,
                 remote_history_completeness_verified=False,
                 segment_count=0,verified_capture_count=0,
                 supplied_catalogue_sha256=None,decoded_capture_bytes=None)
    if report["audit_completed"]:
        details.update(metadata)
    return {**report,**details}
