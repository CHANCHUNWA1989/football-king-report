"""Bounded local intent/outcome audit for cooperative research journal callers."""
import fcntl
import hmac
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path

MAX_BYTES = 1024 * 1024
ACTIONS = {'claim', 'finish', 'halt'}
OUTCOMES = {'GRANTED', 'DENIED', 'HALTED'}


def _payload(seq, previous, action, phase):
    return json.dumps([seq, previous, action, phase], separators=(',', ':')).encode('ascii')


class AuditedGate:
    """Preprovisioned private audit file; no create/reset path or external authorization.

    Requires cooperative callers, a private stable parent, independently retained
    file identity and secret. Valid-prefix rollback is not detected here.
    """
    def __init__(self, gate, path, *, identity, key):
        if (type(identity) is not tuple or len(identity) != 2 or
                any(type(x) is not int or x < 0 for x in identity) or
                type(key) is not bytes or len(key) != 32):
            raise ValueError('INVALID_AUDIT_PIN')
        self.gate, self.path, self.identity, self.key = gate, Path(path), identity, key

    @contextmanager
    def _open(self):
        fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r+b', buffering=0) as f:
            s = os.fstat(fd)
            if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or
                    s.st_mode & 0o077 or s.st_nlink != 1 or
                    (s.st_dev, s.st_ino) != self.identity):
                raise ValueError('UNTRUSTED_AUDIT_FILE')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield f

    def _read(self, f):
        raw = f.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or (raw and not raw.endswith(b'\n')):
            raise ValueError('AUDIT_SIZE_OR_PARTIAL')
        previous, seq, pending = '0'*64, 0, None
        for line in raw.splitlines():
            record = json.loads(line)
            if type(record) is not list or len(record) != 5:
                raise ValueError('AUDIT_RECORD')
            n, prev, action, phase, tag = record
            if type(n) is not int or n != seq + 1 or prev != previous or action not in ACTIONS:
                raise ValueError('AUDIT_SEQUENCE')
            if (pending is None and phase != 'INTENT') or (pending is not None and (action != pending or phase not in OUTCOMES)):
                raise ValueError('AUDIT_PHASE')
            expected = hmac.digest(self.key, _payload(n, prev, action, phase), 'sha256').hex()
            if type(tag) is not str or not hmac.compare_digest(expected, tag):
                raise ValueError('AUDIT_MAC')
            pending = action if phase == 'INTENT' else None
            previous, seq = tag, n
        if pending is not None:
            raise ValueError('UNFINISHED_INTENT')
        return seq, previous

    def _append(self, f, seq, previous, action, phase):
        n = seq + 1
        tag = hmac.digest(self.key, _payload(n, previous, action, phase), 'sha256').hex()
        line = json.dumps([n, previous, action, phase, tag], separators=(',', ':')).encode('ascii') + b'\n'
        f.seek(0, os.SEEK_END)
        if f.tell() + len(line) > MAX_BYTES:
            raise ValueError('AUDIT_CAPACITY')
        if f.write(line) != len(line):
            raise OSError('SHORT_AUDIT_WRITE')
        os.fsync(f.fileno())
        return n, tag

    def _run(self, action, invoke):
        with self._open() as f:
            seq, previous = self._read(f)
            seq, previous = self._append(f, seq, previous, action, 'INTENT')
            result = invoke()
            phase = 'HALTED' if action == 'halt' else 'GRANTED' if result else 'DENIED'
            self._append(f, seq, previous, action, phase)
            return result

    def claim(self, job, *, now):
        return self._run('claim', lambda: self.gate.claim(job, now=now))

    def finish(self, job, *, token, now):
        return self._run('finish', lambda: self.gate.finish(job, token=token, now=now))

    def halt(self):
        # Audit outage must not suppress an emergency stop attempt.
        try:
            return self._run('halt', self.gate.halt)
        except Exception:
            self.gate.halt()
            raise
