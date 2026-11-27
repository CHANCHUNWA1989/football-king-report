"""Private run-scoped evidence storage for V47. POSIX local filesystem only.

Local hashes and access permissions do not authenticate clocks or publishers.
Never upload this archive or expose its contents in a public log. Historical
archive references are retained, not copies of all historical source bytes.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import stat
from .research_live_cohort_directory import open_root,read_at
from .research_live_intake_v4 import decode,unique,bad_constant
from .research_prospective_fusion_v38 import canonical,sha,replay,fingerprint,exact
from .research_private_propline_v43 import private_components
from .research_missing_fixture_discovery_v16 import identity
from .research_candidate_gap_v6 import stamp

MAX_RUN_BYTES=64*1024*1024
MAX_PACKETS=160

def root_fd(directory,repository):
    p=Path(directory)
    if not p.is_absolute():raise ValueError("absolute private directory required")
    repo=Path(repository).resolve()
    resolved=p.resolve()
    if resolved.is_relative_to(repo) or repo.is_relative_to(resolved):
        raise ValueError("private directory must be separate from repository")
    fd=open_root(p)
    info=os.fstat(fd)
    if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:
        os.close(fd);raise ValueError("private directory must be owned with mode 0700")
    return fd

def b64(raw):
    if not isinstance(raw,bytes):raise ValueError("expected bytes")
    return base64.b64encode(raw).decode("ascii")

def unb64(value):
    if not isinstance(value,str):raise ValueError("invalid byte encoding")
    raw=base64.b64decode(value,validate=True)
    if b64(raw)!=value:raise ValueError("noncanonical encoding")
    return raw

def verify_run(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_RUN_BYTES:
        raise ValueError("run size")
    d=json.loads(raw,object_pairs_hook=unique,parse_constant=bad_constant)
    exact(d,"schema forecast_utc batch packets private_only external_witness_verified")
    if d["schema"]!="private-fusion-run-v48" or d["private_only"] is not True or d["external_witness_verified"] is not False:
        raise ValueError("unsafe run")
    now=stamp(d["forecast_utc"]).isoformat()
    batch=d["batch"];exact(batch,"raw league captured_utc")
    market_raw=unb64(batch["raw"])
    components,_=private_components(market_raw,league=batch["league"],
                                   captured_utc=batch["captured_utc"],as_of=now)
    by_id={c["event_id"]:c for c in components}
    packets=d["packets"]
    if not isinstance(packets,list) or not 0<len(packets)<=MAX_PACKETS:
        raise ValueError("invalid packet count")
    seen=set()
    for packet in packets:
        exact(packet,"raw_input receipt market_route history_references private_only")
        if packet["private_only"] is not True:raise ValueError("unsafe packet")
        body=unb64(packet["raw_input"]);doc=decode(body)
        receipt=replay(packet["receipt"],body)
        if receipt["forecast_utc"]!=now or receipt["candidate"]["state"]!="RESEARCH_CANDIDATE":
            raise ValueError("invalid receipt clock or state")
        event=doc["event_id"]
        if event in seen or event not in by_id:raise ValueError("invalid event roster")
        seen.add(event);c=by_id[event];route=packet["market_route"]
        if route!={"route":"PRIVATE_BACKUP_ONLY","component":c,"private_only":True,"upstream_independence_proven":False}:
            raise ValueError("market route mismatch")
        if any(doc[k]!=c[k] for k in ("event_id","league","home","away","kickoff_utc","market")):
            raise ValueError("market input mismatch")
        refs=packet["history_references"]
        if not isinstance(refs,list) or len(refs)!=len(doc["history"]):
            raise ValueError("history reference roster mismatch")
        for row,group in zip(doc["history"],refs):
            if not isinstance(group,list) or len(group) not in (1,2):
                raise ValueError("invalid history references")
            for r in group:
                exact(r,"provider captured_utc provider_id path decoded_sha256")
                if r["provider"] not in ("OpenLigaDB","thesportsdb"):raise ValueError("unknown publisher")
                fingerprint(r["decoded_sha256"])
                if not isinstance(r["path"],str) or not r["path"]:raise ValueError("invalid reference path")
                if not stamp(row["kickoff_utc"])<stamp(r["captured_utc"])<=stamp(row["observed_utc"]):
                    raise ValueError("reference chronology")
            if len({r["provider"] for r in group})!=len(group):raise ValueError("duplicate publisher")
            last=max(group,key=lambda r:(stamp(r["captured_utc"]),r["provider"]))
            if (last["provider"],last["provider_id"],last["decoded_sha256"],stamp(last["captured_utc"]))!=(
                row["source_id"],row["fixture_id"],row["evidence_sha256"],stamp(row["observed_utc"])):
                raise ValueError("history reference mismatch")
    return {"schema":"private-fusion-run-audit-v48","status":"HOLD",
            "local_replay_verified":True,"local_receipts":len(packets),
            "run_sha256":sha(raw),"external_witness_verified":False,
            "historical_reference_bytes_rechecked":False,"cohort_completeness_proven":False,
            "source_authenticity_verified":False,"authenticated_samples":0,
            "publication_allowed":False,"production_recommendations":"DISABLED"}

def encode_run(batch,packets):
    if not isinstance(packets,list) or not 0<len(packets)<=MAX_PACKETS:
        raise ValueError("invalid packet count")
    raw=canonical({"schema":"private-fusion-run-v48",
         "forecast_utc":packets[0]["receipt"]["forecast_utc"],
         "batch":{**batch,"raw":b64(batch["raw"])},
         "packets":[{**p,"raw_input":b64(p["raw_input"])} for p in packets],
         "private_only":True,"external_witness_verified":False})
    verify_run(raw)
    return raw

def save(directory,repository,batch,packets,*,credential=None):
    raw=encode_run(batch,packets)
    # Avoid persisting a reflected credential in a provider response or packet.
    if credential:
        if not isinstance(credential,str):raise ValueError("invalid credential")
        secret=credential.encode()
        if secret in batch["raw"] or secret in raw or any(secret in p["raw_input"] for p in packets):
            raise ValueError("credential reflection rejected")
    digest=sha(raw);name=digest+".json"
    fd=root_fd(directory,repository)
    tmp=".pending-"+secrets.token_hex(16)
    try:
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW
        with os.fdopen(os.open(tmp,flags,0o600,dir_fd=fd),"wb") as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        # Atomic no-replace publication within the private directory.
        os.link(tmp,name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
        os.unlink(tmp,dir_fd=fd)
        os.fsync(fd)
        if read_at(fd,name,MAX_RUN_BYTES)!=raw:raise ValueError("stored bytes mismatch")
        return verify_run(raw)
    finally:
        try:os.unlink(tmp,dir_fd=fd)
        except FileNotFoundError:pass
        os.close(fd)

def load(directory,repository,digest):
    fingerprint(digest)
    fd=root_fd(directory,repository)
    try:
        name=digest+".json"
        info=os.stat(name,dir_fd=fd,follow_symlinks=False)
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError("unsafe file permissions")
        raw=read_at(fd,name,MAX_RUN_BYTES)
        if sha(raw)!=digest:raise ValueError("run digest mismatch")
        return verify_run(raw)
    finally:os.close(fd)


def verify_run_with_history(raw,ledger,primary,secondary,*,include_supplemental):
    """Rebuild the entire V48 run using caller-supplied historical archive bytes.

    Exact replay verifies consistency with this supplied roster only. V48 did
    not commit to the entire original history archive roster at capture time.
    No external time witness, independent source proof or completeness claim.
    """
    from .research_archive_bound_replay_v47 import freeze_archive,MAX_TOTAL_ARCHIVE_BYTES
    from .research_archive_score_recovery_v14 import MAX_FILES as PRIMARY_MAX
    from .research_two_publisher_recovery_v15 import MAX_FILES as SECONDARY_MAX
    from .research_integrated_fusion_v45 import prepare
    from .research_supplemental_provenance_v46 import verify_ref
    from .research_live_intake_v4 import MAX_BYTES
    if type(include_supplemental) is not bool:raise ValueError("invalid history mode")
    if not isinstance(ledger,bytes) or not 0<len(ledger)<=MAX_BYTES:
        raise ValueError("invalid ledger bytes")
    audit=verify_run(raw)
    d=json.loads(raw);now=stamp(d["forecast_utc"])
    a,ap,budget=freeze_archive(primary,PRIMARY_MAX,MAX_TOTAL_ARCHIVE_BYTES)
    b,bp,_=freeze_archive(secondary,SECONDARY_MAX,budget)
    batch={**d["batch"],"raw":unb64(d["batch"]["raw"])}
    packets,report=prepare(ledger,a,b,None,[batch],as_of=now.isoformat(),
                           include_supplemental=include_supplemental)
    if not packets or encode_run(batch,packets)!=raw:
        raise ValueError("full run reconstruction mismatch")
    archives={(provider,label,sha(body)):body
              for provider,items in (("OpenLigaDB",a),("thesportsdb",b))
              for label,body in items}
    doc=decode(packets[0]["raw_input"])
    refs=packets[0]["history_references"]
    if not doc["history"] or len(doc["history"])!=len(refs):
        raise ValueError("empty or inconsistent history")
    for row,group in zip(doc["history"],refs):
        k=identity(row["league"],row["home"],row["away"],row["kickoff_utc"])
        if max(verify_ref(ref,k,row["score"],archives,now) for ref in group)!=stamp(row["observed_utc"]):
            raise ValueError("historical reference clock mismatch")
    # Every packet was regenerated from the same history roster by prepare.
    return {**audit,"historical_reference_bytes_rechecked":True,
            "full_supplied_roster_replay_verified":True,
            "history_candidates":report["history_inventory"]["history_candidates"],
            "include_supplemental":include_supplemental,
            "supplied_archive_binding_sha256":sha(canonical({
                "ledger_sha256":sha(ledger),"primary":ap,"secondary":bp})),
            "original_archive_roster_authenticated":False,
            "training_admission":False,"model_promotion_allowed":False}
