"""Research-only audit with a separately supplied current head and CAS callback."""
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from intelligence_x_audit import AuditedGate, MAX_BYTES


def _head(value):
    if (type(value) is not tuple or len(value) != 2 or type(value[0]) is not int
            or not 0 <= value[0] <= MAX_BYTES or value[0] % 2
            or type(value[1]) is not str or not re.fullmatch('[0-9a-f]{64}', value[1])
            or (value[0] == 0 and value[1] != '0'*64)):
        raise ValueError('INVALID_AUDIT_HEAD')
    return value


class PinnedAuditedGate(AuditedGate):
    """Callbacks must use the same independently trusted, durable audit namespace.

    read_head returns the current (sequence, MAC); advance_head performs a
    durable compare-and-swap and returns exactly True on success. Never
    initialize the trusted head from the candidate log. No witness is provided.
    Cooperative local callers only; old interfaces and privileged writers bypass.
    """
    def __init__(self, gate, path, *, identity, key, read_head, advance_head):
        super().__init__(gate, path, identity=identity, key=key)
        if not callable(read_head) or not callable(advance_head):
            raise ValueError('WITNESS_REQUIRED')
        self.read_head, self.advance_head = read_head, advance_head
        self._serial = threading.Lock()

    def _run(self, action, invoke):
        with self._serial, self._open() as f:
            try:
                old = _head(self.read_head())
                if self._read(f) != old:
                    raise ValueError('AUDIT_HEAD_MISMATCH')
                # Reserve space for both bounded records before any mutation.
                f.seek(0, 2)
                if f.tell() + 512 > MAX_BYTES:
                    raise ValueError('AUDIT_CAPACITY')
                seq, previous = self._append(f, *old, action, 'INTENT')
                result = invoke()
                phase = 'HALTED' if action == 'halt' else 'GRANTED' if result else 'DENIED'
                new = self._append(f, seq, previous, action, phase)
                if self.advance_head(old, new) is not True:
                    raise ValueError('WITNESS_ADVANCE_FAILED')
                return result
            except Exception:
                # A journal mutation may already have committed. Never return a
                # lease/result; attempt quarantine without concealing the failure.
                self.gate.halt()
                raise


def claim_batch(gate, jobs, *, now, workers=4):
    """Bounded research-only batch; queue at most 100; no external execution.

    The audit boundary serializes access. An exception is propagated, not retried;
    previously committed claims are not undone. Use one trusted gate instance.
    """
    if type(gate) is not PinnedAuditedGate:
        raise ValueError('PINNED_GATE_REQUIRED')
    if (type(jobs) is not list or not 1 <= len(jobs) <= 100
            or type(workers) is not int or not 1 <= workers <= 4
            or type(now) is not int or not 0 <= now <= 4102444800
            or any(type(j) is not str or not re.fullmatch('[0-9a-f]{64}', j) for j in jobs)):
        raise ValueError('INVALID_BATCH')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Only aggregate counts leave this synthetic diagnostic; no lease tokens.
        grants = sum(result is not None for result in pool.map(lambda j: gate.claim(j, now=now), jobs))
    return {'total': len(jobs), 'granted': grants, 'denied': len(jobs)-grants,
            'status': 'HOLD', 'production_recommendations': 'DISABLED'}
