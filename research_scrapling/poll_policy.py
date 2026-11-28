"""Single-process research polling policy. No network or source approval."""
from dataclasses import dataclass
from math import isfinite
from threading import Lock


@dataclass
class _Scope:
    due: float = 0
    failures: int = 0
    lease: tuple | None = None
    cached_revision: str | None = None
    pending_revision: str | None = None
    halted: bool = False


class PollPolicy:
    def __init__(self, scopes):
        self._scopes = {scope: _Scope() for scope in scopes}
        self._lock = Lock()
        self._clock = 0
        self._serial = 0

    def _time(self, now):
        if type(now) not in (int, float) or not isfinite(now) or now < self._clock:
            raise ValueError("invalid monotonic clock")
        self._clock = now

    def reserve(self, scope, now):
        """Reserve one simulated request; payload and revision share a budget."""
        with self._lock:
            self._time(now)
            s = self._scopes[scope]
            if s.halted or s.lease is not None or now < s.due:
                return None
            self._serial += 1
            kind = "payload" if s.pending_revision is not None else "revision"
            s.lease = (self._serial, kind)
            s.due = now + 60
            return s.lease

    def finish(self, scope, lease, now, status, revision=None, retry_after=0):
        with self._lock:
            self._time(now)
            s = self._scopes[scope]
            if s.lease is None or s.lease != lease:
                raise ValueError("unknown or completed lease")
            if type(status) is not int or not 100 <= status <= 599:
                raise ValueError("invalid HTTP status")
            if type(retry_after) not in (int, float) or not isfinite(retry_after) or retry_after < 0:
                raise ValueError("invalid retry delay")
            valid_revision = isinstance(revision, str) and 0 < len(revision) <= 256
            ok = status == 200 and valid_revision
            if lease[1] == "payload":
                ok = ok and revision == s.pending_revision
            s.lease = None
            s.due = max(s.due, now + 60, now + retry_after)
            if not ok:
                if lease[1] == "payload" and status == 200:
                    s.pending_revision = None
                s.failures = min(s.failures + 1, 7)
                s.due = max(s.due, now + min(3600, 60 * 2 ** s.failures))
                s.halted = status in (401, 403)
                return "HOLD_ERROR"
            s.failures = 0
            if lease[1] == "payload":
                s.cached_revision = revision
                s.pending_revision = None
                return "RESEARCH_CACHE_REVISION_COMMITTED"
            if revision == s.cached_revision:
                return "UNCHANGED_NOT_FRESH_EVIDENCE"
            s.pending_revision = revision
            return "RESEARCH_PAYLOAD_PENDING"

    def snapshot(self, scope):
        with self._lock:
            s = self._scopes[scope]
            return {"next_eligible": s.due, "failures": s.failures,
                    "halted": s.halted, "in_flight": s.lease is not None,
                    "cached_revision": s.cached_revision,
                    "pending_revision": s.pending_revision,
                    "status": "HOLD", "live_trading": "DISABLED",
                    "production_recommendations": "DISABLED",
                    "model_input_allowed": False, "network_enabled": False}
