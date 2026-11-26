"""Offline reference for a future shared transactional quota coordinator.

Store contract: read() -> immutable State; cas(old,new) -> exact bool,
linearizable, durable, and atomic at the service. No actual backend is supplied.
Never permits network calls, including when a simulated reservation succeeds.
"""
from dataclasses import dataclass
from vnext_quota_ledger_offline import ID, result


@dataclass(frozen=True)
class State:
    epoch: str
    revision: int
    clock: int
    attempts: tuple  # (request_id, consumer, UTC epoch second)


def valid(state, epoch, floor):
    if type(state) is not State or state.epoch != epoch:
        return False
    if type(state.revision) is not int or type(state.clock) is not int:
        return False
    if not (0 <= floor <= state.revision and 0 <= state.clock <= 253402300799):
        return False
    if type(state.attempts) is not tuple or len(state.attempts) > 100000:
        return False
    if state.revision < len(state.attempts):
        return False
    seen = set()
    prev = 0
    for row in state.attempts:
        if type(row) is not tuple or len(row) != 3:
            return False
        rid, consumer, ts = row
        if not all(type(v) is str and ID.fullmatch(v) for v in (rid, consumer)):
            return False
        if rid in seen or type(ts) is not int or not prev <= ts <= state.clock or ts <= 0:
            return False
        seen.add(rid)
        prev = ts
    return True


def reserve_simulated(store, *, epoch, revision_floor, request_id, consumer,
                      now, observed, daily_remaining, minute_remaining):
    if not all(type(v) is str and ID.fullmatch(v) for v in (epoch, request_id, consumer)):
        return result("BAD_ID")
    if not all(type(v) is int for v in (revision_floor, now, observed, daily_remaining, minute_remaining)):
        return result("BAD_EVIDENCE")
    if not (revision_floor >= 0 and 0 < observed <= now <= 253402300799
            and now-observed <= 300 and 2 <= daily_remaining <= 100 and 2 <= minute_remaining <= 10):
        return result("BAD_EVIDENCE")
    # One CAS only. A competing writer must obtain fresh evidence and retry
    # as a new decision; ambiguous commit is never retried here.
    try:
        old = store.read()
        if not valid(old, epoch, revision_floor):
            return result("INVALID_OR_ROLLED_BACK_STATE")
        if now < old.clock:
            return result("CLOCK_ROLLBACK")
        if any(row[0] == request_id for row in old.attempts):
            return result("REPLAY")
        def count_since(start):
            return sum(row[2] >= start for row in old.attempts)
        if (count_since(now-86400) >= 99 or count_since(now-60) >= 9
                or count_since(observed) >= min(daily_remaining, minute_remaining)-1):
            return result("QUOTA_RESERVE")
        if len(old.attempts) >= 100000:
            return result("LEDGER_FULL")
        new = State(epoch, old.revision+1, now, old.attempts+((request_id, consumer, now),))
        committed = store.cas(old, new)
        if committed is False:
            return result("CAS_CONFLICT")
        if committed is not True:
            return result("COMMIT_UNCERTAIN")
        return result("SIMULATED_ONLY", True)
    except Exception:
        return result("STORE_UNAVAILABLE_OR_COMMIT_UNCERTAIN")
