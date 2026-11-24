"""Research-only audit with a separately supplied current head and CAS callback."""
import re
import threading

from intelligence_x_audit import AuditedGate, MAX_BYTES


def _head(value):
    if (type(value) is not tuple or len(value) != 2 or type(value[0]) is not int
            or not 0 <= value[0] <= MAX_BYTES or value[0] % 2
            or type(value[1]) is not str or not re.fullmatch('[0-9a-f]{64}', value[1])
            or (value[0] == 0 and value[1] != '0'*64)):
        raise ValueError('INVALID_AUDIT_HEAD')
    return value


class CompensationFailed(RuntimeError):
    """No result issued; local quarantine could not be confirmed."""
    def __init__(self, original, halt_error):
        super().__init__('QUARANTINE_UNCONFIRMED')
        self.original = original
        self.halt_error = halt_error


class PinnedAuditedGate(AuditedGate):
    """Callbacks must use the same independently trusted, durable audit namespace.

    read_head returns the current (sequence, MAC); advance_head performs a
    durable compare-and-swap and returns exactly True on success. Never
    initialize the trusted head from the candidate log. No witness is provided.
    Cooperative local callers only; old interfaces and privileged writers bypass.
    Compensation halts the whole journal; it is not a distributed transaction.
    """
    def __init__(self, gate, path, *, identity, key, read_head, advance_head):
        super().__init__(gate, path, identity=identity, key=key)
        if not callable(read_head) or not callable(advance_head):
            raise ValueError('WITNESS_REQUIRED')
        self.read_head, self.advance_head = read_head, advance_head
        self._serial = threading.RLock()
        self._failed = False

    def _compensate(self, original):
        self._failed = True
        try:
            self.gate.halt()
        except BaseException as halt_error:
            raise CompensationFailed(original, halt_error) from original

    def _run(self, action, invoke):
        with self._serial:
            if self._failed:
                raise RuntimeError('GATE_FAILED_RESTART_REQUIRES_HALT')
            try:
                with self._open() as f:
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
            except BaseException as original:
                # Includes audit-open errors and interrupts. Never issue a result
                # after ambiguity. This cannot intercept SIGKILL or power loss.
                self._compensate(original)
                raise

    def halt(self):
        # Explicit emergency stop remains callable even if the audit is broken.
        with self._serial:
            if self._failed:
                self.gate.halt()
                return
            try:
                return self._run('halt', self.gate.halt)
            finally:
                self._failed = True

    def recover_halted(self):
        """Explicit conservative startup recovery; never resume old leases."""
        with self._serial:
            self._failed = True
            self.gate.halt()


def claim_batch(gate, jobs, *, now, workers=4):
    """Bounded synthetic diagnostic; serialized; stop dispatch on first failure.

    workers is retained for compatibility, not a concurrency guarantee. On
    failure halt the entire journal, including previously committed claims.
    Success retains synthetic leases; caller must halt before discarding it.
    No external work or authorization.
    """
    if type(gate) is not PinnedAuditedGate:
        raise ValueError('PINNED_GATE_REQUIRED')
    if (type(jobs) is not list or not 1 <= len(jobs) <= 100
            or type(workers) is not int or not 1 <= workers <= 4
            or type(now) is not int or not 0 <= now <= 4102444800
            or any(type(j) is not str or not re.fullmatch('[0-9a-f]{64}', j) for j in jobs)):
        raise ValueError('INVALID_BATCH')
    with gate._serial:
        try:
            grants = sum(gate.claim(j, now=now) is not None for j in jobs)
        except BaseException as original:
            if not gate._failed:
                gate._compensate(original)
            raise
    return {'total': len(jobs), 'granted': grants, 'denied': len(jobs)-grants,
            'status': 'HOLD', 'production_recommendations': 'DISABLED'}
