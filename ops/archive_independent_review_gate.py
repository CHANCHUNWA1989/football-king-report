"""P0 independent reviewer observation. No approval authority and no side effects."""
from datetime import datetime, timedelta, timezone
import json
import hashlib
import argparse
from pathlib import Path
from ops.archive_custody_subject import canonical
from ops.history_blob_retention_preflight import _unique, _valid_sha

REPO_ID = 1411226578
OWNER_ID = 339931460
ARCHIVE = "3ce493fbeb9bfea29af1b93064a085afe8efb280"
LINKED = "5872d05723b8e451b7a73e72c7de610109af55533666ccb5de48233334d30c4b"
CURRENT = "e18e26f6f81cb2ebcc03cddb49a91b81bcc15bea157b249d9ef9f72bad0e4839"
PREVIOUS = "250f37714db76dd78dbb05c275efcb99cbb71f5fb62949c5c4f405a7ddb462e7"
# Intentionally empty until separately reviewed and provisioned outside the PR author.
REVIEWER_IDS = frozenset()
TARGETS = {571: "research/p0-provenance-isolated-branch-pilot-20261123",
           594: "research/p0-pinned35-migration-20261124"}


def utc(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.utcoffset() != timedelta(0):
        raise ValueError("NON_UTC")
    return t


def verify_linked(raw):
    d = json.loads(raw, object_pairs_hook=_unique)
    if (canonical(d) != raw or hashlib.sha256(raw).hexdigest() != LINKED
            or d["schema"] != "football-king-linked-unsigned-custody-v1"
            or d["predecessor_subject_sha256"] != PREVIOUS
            or d["current_subject_sha256"] != CURRENT
            or hashlib.sha256(canonical(d["current_subject"])).hexdigest() != CURRENT
            or d["production_recommendations"] != "DISABLED"):
        raise ValueError("LINKED_SUBJECT_PIN_MISMATCH")
    return LINKED


def assess(pr, reviews, head, now, *, reviewer_ids=REVIEWER_IDS):
    """Pure analysis of API records, never a substitute for independent policy."""
    n = pr["number"]
    if (type(n) is not int or n not in TARGETS or not _valid_sha(head)
            or pr["head"]["sha"] != head or pr["head"]["ref"] != TARGETS[n]
            or pr["head"]["repo"]["id"] != REPO_ID
            or pr["base"]["repo"]["id"] != REPO_ID or pr["base"]["sha"] != ARCHIVE
            or pr["base"]["ref"] != "research/forward-provenance-archive"
            or pr["state"] != "open" or pr.get("merged") is not False):
        raise ValueError("PR_IDENTITY_OR_HEAD_MISMATCH")
    if not isinstance(reviews, list) or len(reviews) >= 100:
        raise ValueError("REVIEW_INVENTORY_NOT_COMPLETE")
    author = pr["user"]["id"]
    if type(author) is not int or author <= 0:
        raise ValueError("INVALID_AUTHOR")
    latest = {}
    seen = set()
    for r in reviews:
        who, rid, state = r["user"]["id"], r["id"], r["state"]
        if (type(who) is not int or who <= 0 or type(rid) is not int or rid <= 0 or rid in seen
                or state not in {"APPROVED","CHANGES_REQUESTED","DISMISSED","COMMENTED","PENDING"}):
            raise ValueError("INVALID_OR_DUPLICATE_REVIEW")
        seen.add(rid)
        if state in {"COMMENTED","PENDING"}:
            continue
        t = utc(r["submitted_at"])
        if t > now:
            raise ValueError("FUTURE_REVIEW")
        if who not in latest or (t,rid) > latest[who][0]:
            latest[who] = ((t,rid),r)
    valid = sorted(who for who,(_,r) in latest.items()
                   if who in reviewer_ids and who not in {author,OWNER_ID}
                   and r["user"].get("type") == "User"
                   and r["state"] == "APPROVED" and r.get("commit_id") == head
                   and r.get("author_association") in {"MEMBER","COLLABORATOR","OWNER"})
    dissent = any(r["state"] == "CHANGES_REQUESTED" for _,r in latest.values())
    return dict(pr=n,head=head,review_count=len(reviews),eligible_review_count=len(valid),
                exact_head_independent_review_observed=bool(valid) and not dissent,
                unresolved_changes_requested=dissent)


def report(prs, linked_bytes, now):
    digest = verify_linked(linked_bytes)
    rows = []
    for p in prs:
        try:
            rows.append(assess(p["pr"],p["reviews"],p["head"],now))
        except ValueError as exc:
            if str(exc) != "PR_IDENTITY_OR_HEAD_MISMATCH":
                raise
            # Preserve the contradiction; never normalize a mismatched base ref or SHA.
            rows.append(dict(pr=p["pr"]["number"],head=p["head"],
                             observed_base_ref=p["pr"]["base"]["ref"],
                             observed_base_sha=p["pr"]["base"]["sha"],
                             reason="PR_IDENTITY_OR_HEAD_MISMATCH",
                             review_count=None,eligible_review_count=0,
                             exact_head_independent_review_observed=False,
                             unresolved_changes_requested=None))
    if {x["pr"] for x in rows} != set(TARGETS) or len(rows) != 2:
        raise ValueError("INCOMPLETE_PR_SET")
    return dict(status="HOLD_INDEPENDENT_WITNESS_APPROVAL_REQUIRED",subject_sha256=digest,
                observations=rows,reviewer_policy_provisioned=bool(REVIEWER_IDS),
                protected_environment_verified=False,tsa_policy_approved=False,
                independent_review_verified=False,external_signing_authorized=False,
                hosted_archive_write_authorized=False,source_switch_authorized=False,
                production_recommendations="DISABLED")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--observations",type=Path,required=True)
    p.add_argument("--subject",type=Path,required=True)
    a=p.parse_args()
    try:
        doc=json.loads(a.observations.read_bytes(),object_pairs_hook=_unique)
        r=report(doc["prs"],a.subject.read_bytes(),utc(doc["observed_utc"]))
        print(json.dumps(r,sort_keys=True))
    except (ValueError,OSError,KeyError,TypeError,AttributeError):
        print(json.dumps(dict(status="HOLD_REVIEW_OBSERVATION_INVALID",production_recommendations="DISABLED")))
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
