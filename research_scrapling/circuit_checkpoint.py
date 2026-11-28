"""Single-writer research checkpoint. Restart always reopens the circuit.
Local file integrity only; not authenticated or rollback-resistant.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime
from dataclasses import replace
from circuit_policy import start, COOLDOWN
from evidence_intake import unique_object

MAX_BYTES=8192
def canonical(doc):
    return json.dumps(doc,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def save(path,state):
    payload={"schema":1,"domain":state.domain,"last_checked":state.last_checked.isoformat(),
             "reopen_until":state.reopen_until.isoformat(),
             "source_captures":[x.isoformat() for x in state.last_source_captures]}
    raw=canonical({"payload":payload,"sha256":hashlib.sha256(canonical(payload)).hexdigest()})
    if len(raw)>MAX_BYTES:raise ValueError("checkpoint too large")
    fd,name=tempfile.mkstemp(prefix=".checkpoint-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def timestamp(value):
    t=datetime.fromisoformat(value)
    if t.tzinfo is None or t.utcoffset() is None:raise ValueError("naive time")
    return t

def restore(path,domain,now):
    state=start(domain,now)
    try:
        with path.open("rb") as stream:raw=stream.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError("checkpoint too large")
        envelope=json.loads(raw,object_pairs_hook=unique_object)
        p=envelope["payload"]
        if set(envelope)!={"payload","sha256"} or envelope["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():
            raise ValueError("integrity")
        if set(p)!={"schema","domain","last_checked","reopen_until","source_captures"} or type(p["schema"]) is not int or p["schema"]!=1 or p["domain"]!=domain:
            raise ValueError("schema or domain")
        last=timestamp(p["last_checked"]);until=timestamp(p["reopen_until"])
        if not isinstance(p["source_captures"],list) or len(p["source_captures"]) not in (0,2):
            raise ValueError("capture count")
        captures=tuple(timestamp(x) for x in p["source_captures"])
        if any(t>last for t in captures):raise ValueError("future capture")
        # Never restore a ready phase or accumulated success count.
        state=replace(state,last_checked=max(now,last),reopen_until=max(now,last)+COOLDOWN,
                      last_capture=min(captures) if captures else None,last_source_captures=captures)
        state=replace(state,reopen_until=max(state.reopen_until,until))
        return state,"RESTORED_OPEN"
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        return state,"RESET_OPEN"
