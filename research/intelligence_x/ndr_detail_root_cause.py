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
    codes={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant)
           and isinstance(n.value,str) and "NDR" in n.value and n.value.isascii()
           and n.value.replace("_","").isalnum() and n.value.isupper() and len(n.value)<=96}
    # _one_in builds its error from a source-authored CSS literal. Permit only
    # the exact statically known call-site values, never a source HTML class.
    for node in ast.walk(tree):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                and node.func.id=="_one_in" and len(node.args)==4
                and isinstance(node.args[3],ast.Constant)
                and isinstance(node.args[3].value,str)):
            css=node.args[3].value
            if css.isascii() and css.replace("-","").isalnum() and len(css)<=64:
                codes.add("MISSING_OR_AMBIGUOUS_NDR_DETAIL_"+css.upper())
                codes.add("CROSS_SCOPE_NDR_DETAIL_"+css.upper())
    return codes

def cardinality(exc,codes):
    # Only report a bounded categorical count from the actual parser's
    # failing _single frame. Never emit nodes, HTML, attributes or locals.
    from ops import ndr_completion_observations as parser
    tb=exc.__traceback__
    while tb:
        frame=tb.tb_frame
        if frame.f_code is parser._single.__code__:
            reason=frame.f_locals.get("reason")
            nodes=frame.f_locals.get("nodes")
            if type(reason) is str and reason in codes and type(nodes) is list:
                return "ZERO" if len(nodes)==0 else "MULTIPLE" if len(nodes)>1 else "ONE"
        tb=tb.tb_next
    return "NOT_AVAILABLE"

def ticker_shape(exc):
    # Inspect only fixed selectors in the already parsed tree at the failed
    # call site. Output bounded counts, never source text or attributes.
    from ops import ndr_completion_observations as parser
    tb=exc.__traceback__
    while tb:
        frame=tb.tb_frame
        if frame.f_code is parser._one_in.__code__:
            loc=frame.f_locals
            if loc.get("tag")=="ul" and loc.get("css")=="liveticker-list":
                article,scope=loc.get("article"),loc.get("scope")
                if type(article) is parser._Node and type(scope) is parser._Node:
                    def count(nodes):
                        return min(len(nodes),100)
                    return {
                        "list_class_in_ticker":count(scope.descendants(css="liveticker-list")),
                        "list_class_in_article":count(article.descendants(css="liveticker-list")),
                        "ul_in_ticker":count(scope.descendants("ul")),
                        "ol_in_ticker":count(scope.descendants("ol")),
                        "event_items_in_ticker":count(scope.descendants(css="liveticker-item")),
                        "event_items_in_article":count(article.descendants(css="liveticker-item")),
                        "end_icons_in_ticker":count([n for n in scope.descendants("img") if n.attrs.get("src")==parser.END_ICON and n.attrs.get("alt")=="Spielende"]),
                        "end_labels_in_ticker":count([n for n in scope.descendants("b") if n.text().strip()=="Spielende"]),
                        "end_icons_in_article":count([n for n in article.descendants("img") if n.attrs.get("src")==parser.END_ICON and n.attrs.get("alt")=="Spielende"]),
                        "end_labels_in_article":count([n for n in article.descendants("b") if n.text().strip()=="Spielende"]),
                    }
        tb=tb.tb_next
    return None

def candidate_selector(original,article,scope,tag,css):
    """Research-only fallback for exactly the observed missing list class."""
    from ops import ndr_completion_observations as parser
    if (tag,css)!=("ul","liveticker-list") or article.descendants(css=css):
        return original(article,scope,tag,css)
    if scope.tag!="div" or "liveticker" not in scope.classes():
        raise ValueError("RESEARCH_TICKER_SCOPE")
    lists=scope.descendants("ul")
    if len(lists)!=1 or scope.descendants("ol"):
        raise ValueError("RESEARCH_TICKER_LIST_AMBIGUOUS")
    listing=lists[0]
    parser._visible(listing)
    events=listing.descendants("li","liveticker-item")
    if (not events or article.descendants(css="liveticker-item")!=events
            or any(event.parent is not listing for event in events)
            or [node for node in listing.children if isinstance(node,parser._Node)]!=events):
        raise ValueError("RESEARCH_TICKER_EVENT_SCOPE")
    return listing

def candidate_replay(detail,row,policy,codes):
    from unittest.mock import patch
    from ops import ndr_completion_observations as parser
    original=parser._one_in
    try:
        with patch.object(parser,"_one_in",side_effect=lambda a,s,t,c: candidate_selector(original,a,s,t,c)):
            result=parse_detail(detail,row,policy=policy)
    except (ValueError,TypeError,RecursionError) as exc:
        safe=codes|{"RESEARCH_TICKER_SCOPE","RESEARCH_TICKER_LIST_AMBIGUOUS","RESEARCH_TICKER_EVENT_SCOPE"}
        return {"status":"REJECTED","reason":classify(exc,safe)[1]}
    require(result.get("independently_verified") is False and result.get("eligible_for_model_scoring") is False and result.get("status")=="HOLD" and result.get("production_recommendations")=="DISABLED","UNSAFE_RESEARCH_RESULT")
    return {"status":"DISPLAY_CANDIDATE_ONLY","reason":"ALL_EXISTING_DOWNSTREAM_CHECKS_PASSED"}

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
    from ops.ndr_completion_observations import _Node, _one_in, _single
    for nodes, expected in (([], "ZERO"), ([object(),object()], "MULTIPLE")):
        try:
            _single(nodes,"MISSING_OR_AMBIGUOUS_NDR_HTML")
        except ValueError as exc:
            require(cardinality(exc,codes)==expected,"CARDINALITY_TEST")
        else:
            raise ValueError("EXPECTED_CARDINALITY_REJECTION")
    root=_Node("article",{})
    try:
        _one_in(root,root,"div","steno-head")
    except ValueError as exc:
        require(classify(exc,codes)==("VALUE_ERROR","MISSING_OR_AMBIGUOUS_NDR_DETAIL_STENO-HEAD"),"DYNAMIC_CODE_TEST")
        require(cardinality(exc,codes)=="ZERO","DYNAMIC_CARDINALITY_TEST")
    else:
        raise ValueError("EXPECTED_DYNAMIC_REJECTION")
    try:
        _single([], "private source string")
    except ValueError as exc:
        require(cardinality(exc,codes)=="NOT_AVAILABLE","UNKNOWN_CARDINALITY_REDACTION")
    else:
        raise ValueError("EXPECTED_UNKNOWN_REJECTION")
    # Missing list, wrong tag and cross-scope cases must remain rejected.
    for shape in ("empty","wrong_tag","outside_scope"):
        root=_Node("article",{})
        scope=_Node("div",{"class":"liveticker"},root)
        root.children.append(scope)
        if shape!="empty":
            parent=scope if shape=="wrong_tag" else root
            listing=_Node("ol" if shape=="wrong_tag" else "ul",{"class":"liveticker-list"},parent)
            parent.children.append(listing)
            event=_Node("li",{"class":"liveticker-item"},listing)
            listing.children.append(event)
        try:
            _one_in(root,scope,"ul","liveticker-list")
        except ValueError as exc:
            data=ticker_shape(exc)
            require(data is not None,"TICKER_SHAPE_MISSING")
            require(data["list_class_in_ticker"]==int(shape=="wrong_tag"),"TICKER_SCOPE_TEST")
            require(data["list_class_in_article"]==int(shape!="empty"),"ARTICLE_SCOPE_TEST")
            require(data["event_items_in_ticker"]==int(shape=="wrong_tag"),"EVENT_SCOPE_TEST")
            require(data["end_icons_in_ticker"]==data["end_labels_in_article"]==0,"NO_END_MARKER_TEST")
        else:
            raise ValueError("EXPECTED_TICKER_REJECTION")
    require(ticker_shape(ValueError("private")) is None,"UNRELATED_ERROR_REDACTION")
    # Exercise only the new selector, including visibility and scope attacks.
    for variant in ("valid","extra_list","hidden","foreign_event","nested_event","wrong_tag","existing_class"):
        article=_Node("article",{})
        scope=_Node("div",{"class":"liveticker"},article)
        article.children.append(scope)
        attrs={"hidden":""} if variant=="hidden" else {"class":"liveticker-list"} if variant=="existing_class" else {}
        listing=_Node("ol" if variant=="wrong_tag" else "ul",attrs,scope)
        scope.children.append(listing)
        event=_Node("li",{"class":"liveticker-item"},listing)
        listing.children.append(event)
        if variant=="extra_list":
            scope.children.append(_Node("ul",{},scope))
        if variant=="foreign_event":
            article.children.append(_Node("li",{"class":"liveticker-item"},article))
        if variant=="nested_event":
            event.children.append(_Node("li",{"class":"liveticker-item"},event))
        try:
            got=candidate_selector(_one_in,article,scope,"ul","liveticker-list")
        except ValueError:
            require(variant not in ("valid","existing_class"),"UNEXPECTED_SELECTOR_REJECTION")
        else:
            require(variant in ("valid","existing_class") and got is listing,"UNSAFE_SELECTOR_ACCEPTANCE")
    return 19

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
                                        "selector_cardinality":cardinality(exc,codes),
                                        "ticker_shape":ticker_shape(exc),
                                        "experimental_replay":candidate_replay(detail,rows[mid],policy,codes),
                                        "original_reason":rejected["reason"],"raw_bytes_present":True})
                else:
                    raise ValueError("ORIGINAL_REJECTION_NOT_REPRODUCED")
    require(len(diagnostics)==4,"EXPECTED_FOUR_ORIGINAL_REJECTIONS")
    print(json.dumps({"schema":"intelligence-x-ndr-detail-root-cause-v4","cases":diagnostics,
                      "reproduced_rejections":len(diagnostics),"category_counts":dict(Counter(x["category"] for x in diagnostics)),
                      "reason_counts":dict(Counter(x["reason"] for x in diagnostics)),"synthetic_tests":tested,
                      "production_parser_modified":False,"experimental_display_candidates":sum(x["experimental_replay"]["status"]=="DISPLAY_CANDIDATE_ONLY" for x in diagnostics),"authenticated_settlements":0,
                      "eligible_for_model_scoring":False,"status":"HOLD","production_recommendations":"DISABLED"},sort_keys=True))
if __name__=="__main__":
    main()
