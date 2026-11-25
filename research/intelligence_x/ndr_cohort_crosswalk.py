"""Candidate-only cross-publisher index join; never authenticate source independence."""
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unicodedata
from ops.ndr_capture_provenance import audit
from ops.ndr_capture_pack import _members
from ops.ndr_result_observations import _ResultsParser, _row_observation, parse_html
from replay_ndr_archives import ARCHIVE_HEAD, PACKS, git_blob, unpack, require

COHORT_BLOB = "12e72d988ae80081376f43aa510e910239c9d3f4"

def norm(value):
    require(isinstance(value, str), "BAD_TEAM_LABEL")
    return "".join(c for c in unicodedata.normalize("NFKD", value).lower()
                   if c.isascii() and c.isalnum())

def accepted_labels(raw):
    accepted, _ = parse_html(raw)
    expected = {r["provider_fixture_id"]: r for r in accepted}
    parser = _ResultsParser()
    parser.feed(raw.decode("utf-8"))
    parser.close()
    labels = []
    for row in parser.tables[0].descendants("tr", "sport-match"):
        try:
            obs = _row_observation(row)
        except ValueError:
            continue
        mid = obs["provider_fixture_id"]
        require(obs == expected[mid], "ROW_REPLAY_MISMATCH")
        names = [norm(w.descendants("a")[0].descendants(css="teamname")[0].text())
                 for w in row.descendants(css="teamwrapper")]
        require(len(names)==2 and all(names) and names[0]!=names[1], "BAD_LABEL_PAIR")
        labels.append({"ndr_id":mid, "home_team_id":obs["home_provider_team_id"],
                       "away_team_id":obs["away_provider_team_id"],
                       "home":names[0], "away":names[1], "day":obs["date_local"],
                       "score":[obs["display_score"]["home"],obs["display_score"]["away"]]})
    require(len(labels)==len(expected), "INDEX_COVERAGE_MISMATCH")
    return labels

def join(cases, rows):
    by_id = {}
    team_ids = {}
    labels_to_ids = {}
    for row in rows:
        mid = row["ndr_id"]
        by_id.setdefault(mid, []).append(row)
        for side in ("home","away"):
            team_ids.setdefault(row[side+"_team_id"],set()).add(row[side])
            labels_to_ids.setdefault(row[side],set()).add(row[side+"_team_id"])
    conflicted = {mid for mid, group in by_id.items() if any(x!=group[0] for x in group)}
    unique = [group[0] for mid, group in by_id.items() if mid not in conflicted]
    result = []
    for c in cases:
        league,home,away,utc = json.loads(c["archive_key"])
        require(league=="bundesliga", "WRONG_LEAGUE")
        dt = datetime.fromisoformat(utc)
        require(dt.tzinfo is not None, "NAIVE_KICKOFF")
        day = dt.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()
        all_matches = [x for x in rows if (x["day"],x["home"],x["away"])==(day,home,away)]
        matches = [x for x in unique if (x["day"],x["home"],x["away"])==(day,home,away)]
        reason = "NO_EXACT_ORDERED_LABEL_DATE"
        if any(x["ndr_id"] in conflicted for x in all_matches) or len(matches)>1:
            reason = "AMBIGUOUS_OR_CONFLICTING_NATIVE_ID"
        elif len(matches)==1:
            x=matches[0]
            if any(len(team_ids[x[s+"_team_id"]])!=1 or len(labels_to_ids[x[s]])!=1 for s in ("home","away")):
                reason="AMBIGUOUS_TEAM_LABEL_NATIVE_ID"
            else:
                reason="INDEX_SCORE_AGREEMENT_CANDIDATE" if x["score"]==c["published_score_ft"] else "INDEX_SCORE_CONFLICT"
        result.append({"openliga_id_claim":c["provider_fixture_id_hint"],
                       "ndr_id_candidate":matches[0]["ndr_id"] if len(matches)==1 and reason in ("INDEX_SCORE_AGREEMENT_CANDIDATE","INDEX_SCORE_CONFLICT") else None,
                       "reason":reason,"independently_verified":False})
    return result

def tests():
    c={"archive_key":json.dumps(["bundesliga","a","b","2026-11-06T19:30:00+00:00"]),
       "provider_fixture_id_hint":"1","published_score_ft":[2,1]}
    r={"ndr_id":"2","home_team_id":"10","away_team_id":"11","home":"a","away":"b","day":"2026-11-06","score":[2,1]}
    def reason(rows): return join([c],rows)[0]["reason"]
    require(reason([r])=="INDEX_SCORE_AGREEMENT_CANDIDATE","TEST_POSITIVE")
    require(reason([r,r])=="INDEX_SCORE_AGREEMENT_CANDIDATE","TEST_REPEAT")
    require(reason([dict(r,score=[1,2])])=="INDEX_SCORE_CONFLICT","TEST_SCORE")
    require(reason([r,dict(r,score=[1,2])])=="AMBIGUOUS_OR_CONFLICTING_NATIVE_ID","TEST_CONFLICT")
    require(reason([r,dict(r,ndr_id="3")])=="AMBIGUOUS_OR_CONFLICTING_NATIVE_ID","TEST_DUPLICATE")
    require(reason([dict(r,home="b",away="a")])=="NO_EXACT_ORDERED_LABEL_DATE","TEST_REVERSED")
    require(reason([dict(r,day="2026-11-07")])=="NO_EXACT_ORDERED_LABEL_DATE","TEST_DATE")
    require(reason([r,dict(r,ndr_id="3",day="2026-11-07",home_team_id="12")])=="AMBIGUOUS_TEAM_LABEL_NATIVE_ID","TEST_ALIAS")
    return 8

def main():
    test_count=tests()
    root=Path("archive-input")
    require(subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()==ARCHIVE_HEAD,"ARCHIVE_HEAD")
    cohort=Path("research/intelligence_x/ft_observation_review_20261125.json").read_bytes()
    require(git_blob(cohort)==COHORT_BLOB,"COHORT_BLOB")
    cases=json.loads(cohort)["cases"]
    require(len(cases)==10 and {int(c["provider_fixture_id_hint"]) for c in cases}==set(range(83228,83238)),"COHORT_IDS")
    rows=[]
    rejection_counts=Counter()
    pack_count=0
    for day,run,head,tar_pin,bundle_pin in PACKS:
        source=root/"ndr_capture_provenance"/"2026"/"11"/day/(run+"-1")
        with tempfile.TemporaryDirectory() as tmp:
            proof=Path(tmp)
            tar=unpack(source/"ndr-capture.tar.gz",tar_pin,16_000_000)
            (proof/"ndr-capture.tar").write_bytes(tar)
            (proof/"capture.sigstore.json").write_bytes(unpack(source/"capture.sigstore.json.gz",bundle_pin,2_000_000))
            checked=audit(proof,source_sha=head,workflow_sha=head,run_id=run,attempt="1")
            require(checked.get("audit_completed") is True and checked.get("capture_content_replayed") is True
                    and checked.get("independently_verified") is False,"NDR_REPLAY_FAILED")
            files=_members(tar)
            extracted=accepted_labels(files["ndr.html"]) if "ndr.html" in files else []
            require(len(extracted)==checked["capture_summary"]["index_observation_count"],"INDEX_COUNT")
            rows.extend(extracted)
            report=json.loads(files["report.json"])
            for entry in report.get("rejections",[])+report.get("fetch_errors",[]):
                reason=entry.get("reason","UNKNOWN")
                require(isinstance(reason,str) and len(reason)<=120,"BAD_REASON")
                rejection_counts[reason]+=1
            pack_count+=1
    joined=join(cases,rows)
    print(json.dumps({"schema":"intelligence-x-ndr-crosswalk-diagnostic-v1","packs_reverified":pack_count,
        "tests_passed":test_count,"index_rows":len(rows),"rejection_counts":dict(rejection_counts),
        "cases":joined,"reason_counts":dict(Counter(x["reason"] for x in joined)),
        "actual_kickoff_authenticated":False,"independent_upstream_authenticated":False,
        "authenticated_settlements":0,"eligible_for_model_scoring":False,"status":"HOLD",
        "production_recommendations":"DISABLED"},sort_keys=True))
if __name__=="__main__":
    main()
