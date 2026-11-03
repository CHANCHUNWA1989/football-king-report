"""Offline execution of the REAL BSD archive shell via a deny-by-default fake gh.

Unlike static grep tests, this runs the archive step extracted from the
proposed GitHub Actions YAML. It exercises branch-qualified GET/PUT, CAS SHA,
status chronology and missing-branch refusal with NO network or credentials.
It is NOT an authorized live GitHub write canary or external review.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bsd_free import collect

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = "archive/bsd-free-research-v1"

# The CLI adapter refuses any endpoint or ref not matching the fixture.
# It has no HTTP code, no github credential and no real gh binary.
FAKE_GH = r'''#!/usr/bin/env python3
import base64,hashlib,json,os,sys
from pathlib import Path
args=sys.argv[1:]
root=Path(os.environ["FAKE_GH_STATE"])
state=json.loads(root.read_text(encoding="utf-8"))
if not args or args[0]!="api":
    sys.exit("FAKE_GH_REJECT_UNLISTED_COMMAND")
args=args[1:]
is_put= len(args)>1 and args[0]=="-X" and args[1]=="PUT"
if is_put:args=args[2:]
if not args:sys.exit("FAKE_GH_MISSING_ENDPOINT")
endpoint=args[0]
flags=args[1:]
fields={}
jq=None
i=0
while i<len(flags):
    if flags[i]=="-f" and i+1<len(flags):
        k,v=flags[i+1].split("=",1)
        if k in fields:sys.exit("FAKE_GH_DUPLICATE_FIELD")
        fields[k]=v
        i+=2
    elif flags[i]=="--jq" and i+1<len(flags):
        jq=flags[i+1];i+=2
    else:
        sys.exit("FAKE_GH_INVALID_FLAG")
base="repos/"+os.environ["GITHUB_REPOSITORY"]+"/"
ref=state["archive_ref"]
if endpoint==base+"git/ref/heads/"+ref and not is_put and jq==".object.sha":
    if not state["branch_exists"]:sys.exit(1)
    print(state["head_sha"])
    sys.exit(0)
prefix=base+"contents/"
if not endpoint.startswith(prefix):
    sys.exit("FAKE_GH_UNEXPECTED_ENDPOINT")
path=endpoint[len(prefix):]
if is_put:
    if not state["branch_exists"]:sys.exit(1)
    if fields.get("branch")!=ref:
        sys.exit("FAKE_GH_FORBIDDEN_DEFAULT_MAIN_WRITE")
    if "content" not in fields or "message" not in fields:
        sys.exit("FAKE_GH_INCOMPLETE_PUT")
    if not path.startswith("sources/bsd_") and not path.startswith("sources/bsd_history/"):
        sys.exit("FAKE_GH_UNAPPROVED_DATA_PATH")
    try:
        content=base64.b64decode(fields["content"],validate=True)
    except ValueError:
        sys.exit("FAKE_GH_INVALID_BASE64")
    if len(content)>1_000_000:
        sys.exit("FAKE_GH_OVERSIZED_CONTENT")
    previous=state["files"].get(path)
    expected=hashlib.sha256(base64.b64decode(previous)).hexdigest() if previous is not None else None
    if fields.get("sha")!=expected:
        sys.exit(1)  # exact compare-and-swap; no clobber
    state["files"][path]=base64.b64encode(content).decode("ascii")
    state["writes"].append({"branch":fields["branch"],"path":path,
                            "had_sha":expected is not None})
    root.write_text(json.dumps(state,sort_keys=True),encoding="utf-8")
    print('{"commit":{"sha":"'+("f"*40)+'"}}')
    sys.exit(0)
if "?ref=" not in path:
    sys.exit("FAKE_GH_REF_REQUIRED")
path,query_ref=path.rsplit("?ref=",1)
if query_ref!=ref:
    sys.exit("FAKE_GH_BAD_READ_BRANCH")
value=state["files"].get(path)
if value is None:sys.exit(1)
data=base64.b64decode(value)
if jq==".sha":
    print(hashlib.sha256(data).hexdigest())
elif jq==".content":
    print(value)
else:
    sys.exit("FAKE_GH_INVALID_CONTENT_SELECTOR")
'''


def archive_script():
    text=(ROOT/".github/workflows/football-king-bsd-free.yml").read_text(
        encoding="utf-8")
    marker="      - name: Save latest provider status and qualified derived market separately\n"
    if text.count(marker)!=1:
        raise ValueError("BSD_ARCHIVE_ACTION_NOT_UNIQUE")
    tail=text.split(marker,1)[1].split("\n  report_failure:\n",1)[0]
    if tail.count("        run: |\n")!=1:
        raise ValueError("BSD_ARCHIVE_RUN_BLOCK_NOT_UNIQUE")
    step=tail.split("        run: |\n",1)[1]
    if not step.startswith("          set -euo pipefail"):
        raise ValueError("BSD_ARCHIVE_SHELL_ANCHOR_CHANGED")
    if "          " not in step:
        raise ValueError("BSD_EMPTY_SCRIPT")
    # Reject any yaml step at the same level nested in this block.
    if "\n      - name:" in step or "\n    steps:" in step:
        raise ValueError("BSD_ARCHIVE_SCRIPT_BOUNDARY_CHANGED")
    return textwrap.dedent(step)


def fake_state(*, existing=None, branch_exists=True):
    return {
        "archive_ref":ARCHIVE, "branch_exists":branch_exists,
        "head_sha":"a"*40,
        "files":{k:base64.b64encode(v).decode("ascii")
                 for k,v in (existing or {}).items()},
        "writes":[],
    }


def execute_archive(tmp, document, *, state, attempt="1"):
    work=Path(tmp)
    # Execute the real checked-out ops/bsd_guard.py from the isolated
    # temporary working directory without copying or altering repo files.
    (work/"ops").symlink_to(ROOT/"ops", target_is_directory=True)
    (work/"bsd").mkdir(exist_ok=True)
    (work/"bsd"/"bsd-result.json").write_text(
        json.dumps(document,ensure_ascii=False),encoding="utf-8")
    bin_dir=work/"fake-bin"
    bin_dir.mkdir(exist_ok=True)
    shim=bin_dir/"gh"
    shim.write_text(FAKE_GH,encoding="utf-8")
    shim.chmod(0o755)
    state_path=work/"fake-gh-state.json"
    state_path.write_text(json.dumps(state,sort_keys=True),encoding="utf-8")
    temp=work/"runner-temp"
    temp.mkdir(exist_ok=True)
    env=dict(os.environ,
             PATH=str(bin_dir)+os.pathsep+os.environ.get("PATH",""),
             FAKE_GH_STATE=str(state_path),
             GITHUB_REPOSITORY="CHANCHUNWA1989/football-king-report",
             GITHUB_RUN_ID="88800000",GITHUB_RUN_ATTEMPT=attempt,
             BSD_ARCHIVE_REF=ARCHIVE,RUNNER_TEMP=str(temp))
    # Shell can only call fake gh from the temp PATH. Never pass a GitHub token.
    for key in ("GH_TOKEN","GITHUB_TOKEN","BSD_FREE_API_TOKEN"):
        env.pop(key,None)
    result=subprocess.run(["bash","-c",archive_script()],
                          cwd=work,env=env,text=True,capture_output=True,
                          timeout=20,check=False)
    return result,json.loads(state_path.read_text(encoding="utf-8"))


class BSDArchiveShellExecutionTests(unittest.TestCase):
    def make_doc(self, *, minutes_ago=0):
        now=datetime.now(timezone.utc)-timedelta(minutes=minutes_ago)
        return collect(now=now,token="")

    def test_real_archiver_shell_only_writes_pinned_data_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,state=execute_archive(
                tmp,self.make_doc(),state=fake_state())
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            self.assertEqual(len(state["writes"]),2)
            self.assertTrue(all(x["branch"]==ARCHIVE for x in state["writes"]))
            self.assertEqual({x["path"] for x in state["writes"] if
                             "/bsd_history/" not in x["path"]},
                             {"sources/bsd_status_latest.json"})
            self.assertEqual(
                json.loads(base64.b64decode(
                    state["files"]["sources/bsd_status_latest.json"]))["status"],
                "NOT_CONFIGURED")

    def test_existing_newer_status_not_overwritten_by_older_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            current=self.make_doc(minutes_ago=0)
            old=self.make_doc(minutes_ago=30)
            existing={"sources/bsd_status_latest.json":
                      json.dumps(current).encode("utf-8")}
            result,state=execute_archive(
                tmp,old,state=fake_state(existing=existing),attempt="2")
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            self.assertIn("Newer BSD snapshot retained",result.stdout)
            self.assertTrue(all(x["path"]!="sources/bsd_status_latest.json"
                                for x in state["writes"]))
            self.assertEqual(base64.b64decode(
                state["files"]["sources/bsd_status_latest.json"]),
                existing["sources/bsd_status_latest.json"])

    def test_missing_archive_branch_fails_without_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,state=execute_archive(
                tmp,self.make_doc(),state=fake_state(branch_exists=False))
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(state["writes"],[])
            self.assertNotIn("sources/bsd_status_latest.json",state["files"])

    def test_branch_mismatch_on_actual_shell_is_refused_by_pinned_guard(self):
        script=archive_script()
        self.assertIn('test "$BSD_ARCHIVE_REF" = "archive/bsd-free-research-v1"',script)
        self.assertEqual(script.count('-f branch="$BSD_ARCHIVE_REF"'),2)
        self.assertEqual(script.count("contents/$target?ref=$BSD_ARCHIVE_REF"),2)
        self.assertNotIn("refs/heads/main",script)
        self.assertNotIn("gh api -X PUT",script.replace(
            'gh api -X PUT "repos/$GITHUB_REPOSITORY/contents/$target"', ""))

    def test_same_timestamp_conflicting_state_fails_closed_no_status_put(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc=self.make_doc()
            existing=dict(doc)
            existing["status"]="NO_COMPARABLE_MARKET"
            existing_blob=json.dumps(existing).encode("utf-8")
            result,state=execute_archive(
                tmp,doc,state=fake_state(existing={
                    "sources/bsd_status_latest.json":existing_blob}))
            self.assertNotEqual(result.returncode,0)
            self.assertTrue(all(x["path"]!="sources/bsd_status_latest.json"
                                for x in state["writes"]))
            self.assertEqual(base64.b64decode(
                state["files"]["sources/bsd_status_latest.json"]),
                existing_blob)


if __name__=="__main__":
    unittest.main()
