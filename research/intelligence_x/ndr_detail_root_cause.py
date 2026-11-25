"""Replay original rejected NDR details and classify failures without changing acceptance."""
import ast
from collections import Counter
import json
from pathlib import Path
import subprocess
import tempfile
from ops.ndr_capture_provenance import audit
from ops.ndr_capture_pack import _members
from ops.ndr_completion_observations import parse_detail, NEW_POLICY, LEGACY_POLICY
from ops.ndr_result_observations import observe
from replay_ndr_archives import ARCHIVE_HEAD, PACKS, unpack, require

def source_codes():
    # Only literal error codes authored in the parser may be published.
    tree=ast.parse(Path("ops/ndr_completion_observations.py").read_text())
    return {n.value for n in ast.walk(tree) if isinstance(n,ast.Constant)
            and isinstance(n.value,str) and "NDR" in n.value and n.value.isascii()
            and n.value.replace("_","").isalnum() and n.value.isupper() and len(n.value)<=96}

def classify(exc,codes):
    if isinstance(exc,ValueError) and str(exc) in codes:
        return "VALUE_ERROR",str(exc)
    if isinstance(exc,TypeError):
        return "TYPE_ERROR","REVIEW_PARSER_OR_INPUT_CONTRACT"
    if isinstance(exc,RecursionError):
        return "RECURSION_ERROR","REVIEW_PARSER_DEPTH"
    return "OTHER_VALUE_ERROR","UNCLASSIFIED_VALUE_ERROR"

def selftest(codes):
    require(classify(ValueError("INVALID_EXPECTED_NDR_ROW"),codes)==("VALUE_ERROR","INVALID_EXPECTED_NDR_ROW"),"KNOWN_ERROR_TEST")
    require(classify(ValueError("arbitrary private source content"),codes)==("OTHER_VALUE_ERROR","UNCLASSIFIED_VALUE_ERROR"),"REDACTION_TEST")
    require(classify(TypeError("arbitrary details"),codes)==("TYPE_ERROR","REVIEW_PARSER_OR_INPUT_CONTRACT"),"TYPE_TEST")
    require(classify(RecursionError("arbitrary details"),codes)==("RECURSION_ERROR","REVIEW_PARSER_DEPTH"),"RECURSION_TEST")
    return 4

def main():
    codes=source_codes()
    tested=selftest(codes)
    archive=Path("archive-input")
    require(subprocess.check_output(["git","-C",str(archive),"rev-parse","HEAD"],text=True).strip()==ARCHIVE_HEAD,"ARCHIVE_HEAD")
    diagnostics=[]
    for day,run,head,tar_pin,bundle_pin in PACKS:
        root=archive/"ndr_capture_provenance"/"2026"/"11"/day/(run+"-1")
        with tempfile.TemporaryDirectory() as temp:
            proof=Path(temp)
            raw=unpack(root/"ndr-capture.tar.gz",tar_pin,16_000_000)
            (proof/"ndr-capture.tar").write_bytes(raw)
            (proof/"capture.sigstore.json").write_bytes(unpack(root/"capture.sigstore.json.gz",bundle_pin,2_000_000))
            checked=audit(proof,source_sha=head,workflow_sha=head,run_id=run,attempt="1")
            require(checked.get("audit_completed") is True and checked.get("capture_content_replayed") is True
                    and checked.get("independently_verified") is False,"NDR_REPLAY_FAILED")
            files=_members(raw)
            report=json.loads(files["report.json"])
            folder=proof/"index";folder.mkdir()
            (folder/"manifest.json").write_bytes(files["index-manifest.json"])
            if "ndr.html" in files:
                (folder/"ndr.html").write_bytes(files["ndr.html"])
            index=observe(folder)
            rows={r["provider_fixture_id"]:r for r in index["observations"]}
            policy=NEW_POLICY if report["schema"]=="football-king-ndr-completion-observations-v3" else LEGACY_POLICY
            for rejected in report["rejections"]:
                mid=rejected["provider_fixture_id"]
                require(mid in rows,"MISSING_INDEX_ROW")
                detail=files["ndr-detail-"+mid+".html"]
                try:
                    parse_detail(detail,rows[mid],policy=policy)
                except (ValueError,TypeError,RecursionError) as exc:
                    category,reason=classify(exc,codes)
                    # Record only the function name at the innermost parser frame,
                    # never source text, exception strings or raw HTML.
                    tb=exc.__traceback__
                    functions=[]
                    while tb:
                        filename=Path(tb.tb_frame.f_code.co_filename).name
                        if filename=="ndr_completion_observations.py":
                            functions.append(tb.tb_frame.f_code.co_name)
                        tb=tb.tb_next
                    diagnostics.append({"run":run,"native_id":mid,"category":category,"reason":reason,
                                        "parser_function":functions[-1] if functions else None,
                                        "original_reason":rejected["reason"],"raw_bytes_present":True})
                else:
                    raise ValueError("ORIGINAL_REJECTION_NOT_REPRODUCED")
    require(len(diagnostics)==4,"EXPECTED_FOUR_ORIGINAL_REJECTIONS")
    print(json.dumps({"schema":"intelligence-x-ndr-detail-root-cause-v1","cases":diagnostics,
                      "reproduced_rejections":len(diagnostics),"category_counts":dict(Counter(x["category"] for x in diagnostics)),
                      "reason_counts":dict(Counter(x["reason"] for x in diagnostics)),"synthetic_tests":tested,
                      "parser_acceptance_modified":False,"authenticated_settlements":0,
                      "eligible_for_model_scoring":False,"status":"HOLD","production_recommendations":"DISABLED"},sort_keys=True))
if __name__=="__main__":
    main()
