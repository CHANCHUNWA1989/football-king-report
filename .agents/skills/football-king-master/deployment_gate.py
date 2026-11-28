"""V3.5 read-only deployment eligibility audit. Never authorizes deployment."""
import argparse
import json
from pathlib import Path
import continuity as v
import remote_anchor as a
import git_state_anchor as g

REPO=v.REPO
REQUIRED=("Football King Master Skill contracts","Football offline 1X2 validation","Unified prediction ledger tests","Repository Safety Check","足球王者｜安全回歸測試")
FLAGS=dict(**a.FLAGS)
def require(ok,reason):
    if not ok: raise ValueError(reason)
def assess(head,pr,main,anchor,main_rules,anchor_rules,reviews,collaborators,runs):
    g.oid(head)
    require(pr["number"]==788 and pr["head"]["sha"]==head and pr["head"]["repo"]["full_name"]==REPO and pr["base"]["repo"]["full_name"]==REPO and pr["base"]["ref"]=="main" and pr["state"]=="open","PR_IDENTITY")
    require(main["name"]=="main" and g.oid(main["commit"]["sha"]),"MAIN_IDENTITY")
    require(anchor["name"]==a.BRANCH and anchor["commit"]["sha"]==a.TIP,"ANCHOR_IDENTITY")
    author=pr["user"]["login"]
    rv=g.review_gate(head,author,reviews)
    require(isinstance(runs,list),"CI_SCHEMA")
    ci={}
    for name in REQUIRED:
        found=[r for r in runs if r.get("name")==name and r.get("head_sha")==head and r.get("event")=="pull_request" and r.get("repository",{}).get("full_name")==REPO]
        ci[name]="AMBIGUOUS" if len(found)>1 else "MISSING" if not found else "PASS" if found[0].get("status")=="completed" and found[0].get("conclusion")=="success" else "NOT_PASSED"
    count=sum(x=="PASS" for x in ci.values())
    pm=a.protection(main,main_rules);pa=a.protection(anchor,anchor_rules)
    blockers=[]
    if count!=len(REQUIRED): blockers.append("EXACT_HEAD_CI_INCOMPLETE")
    for key,info,needed in (("MAIN",pm,{"non_fast_forward","deletion","pull_request"}),("ANCHOR",pa,{"non_fast_forward","deletion"})):
        if info["protectedReported"] is not True: blockers.append(key+"_UNPROTECTED_OR_UNKNOWN")
        if info["activeRuleTypes"] is None or not needed<=set(info["activeRuleTypes"]): blockers.append(key+"_RULES_UNKNOWN_OR_INCOMPLETE")
    eligible=None
    if isinstance(collaborators,list):
        eligible=len({r["login"].lower() for r in collaborators if isinstance(r,dict) and isinstance(r.get("login"),str) and r["login"].lower()!=author.lower() and isinstance(r.get("permissions"),dict) and r["permissions"].get("push") is True})
    requested=pr.get("requested_reviewers")
    requested_count=len(requested) if isinstance(requested,list) else None
    if rv["blockingReviews"]: blockers.append("CHANGES_REQUESTED")
    blockers.extend(["INDEPENDENT_REVIEW_UNVERIFIED","PROTECTION_ENFORCEMENT_UNVERIFIED","PRODUCTION_ANCHOR_UNAUTHENTICATED","SCHEDULE_AND_COST_APPROVAL_UNVERIFIED","CONTINUOUS_OPERATION_UNVERIFIED"])
    return dict(**FLAGS,headSha=head,ciPassed=count,ciRequired=len(REQUIRED),ci=ci,mainProtectedReported=pm["protectedReported"],mainRuleTypes=pm["activeRuleTypes"],anchorProtectedReported=pa["protectedReported"],anchorRuleTypes=pa["activeRuleTypes"],reviewCount=rv["reviewCount"],candidateApprovals=rv["candidateApprovals"],blockingReviews=rv["blockingReviews"],requestedReviewerCount=requested_count,eligibleCollaboratorCandidates=eligible,blockers=blockers,qualification="HOLD",classification="READ_ONLY_METADATA_AUDIT")
def main():
    p=argparse.ArgumentParser();p.add_argument("directory",type=Path);p.add_argument("head");args=p.parse_args()
    try:
        def load(name): return json.loads(v.read(args.directory/(name+".json")))
        out=assess(args.head,load("pr"),load("main"),load("anchor"),load("main-rules"),load("anchor-rules"),load("reviews"),load("collaborators"),load("runs"))
        for name in ("main","anchor"):
            classic=load(name+"-classic")
            out[name+"ClassicProtectionReadable"]=isinstance(classic,dict)
            if isinstance(classic,dict):
                out[name+"ClassicProtectionSummary"]={k:classic.get(k,{}).get("enabled") if isinstance(classic.get(k),dict) else None for k in ("enforce_admins","allow_force_pushes","allow_deletions")}
        print(json.dumps(out,sort_keys=True));return 0
    except Exception as e:
        print(json.dumps(dict(**FLAGS,status="BLOCKED",reason=str(e) if isinstance(e,ValueError) else type(e).__name__)))
        return 1
if __name__=="__main__": raise SystemExit(main())
