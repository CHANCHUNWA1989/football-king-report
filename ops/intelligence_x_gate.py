"""Cooperative local research journal gate. Never authorizes external work."""
import fcntl
import os
import stat
from contextlib import contextmanager
from pathlib import Path

import intelligence_x_job_journal as journal

LATCH = 'QUARANTINED'


def _identity(s):
    return (s.st_dev, s.st_ino)


class JournalGate:
    """Pinned identities come from trusted provisioning, not the current candidate.

    Private stable directories, local Linux filesystem, all callers use this gate.
    No reset, no protection from a privileged writer, old API or external side effects.
    """
    def __init__(self, path, state_dir, *, journal_identity, state_identity):
        self.path = Path(path).absolute()
        self.state_dir = Path(state_dir).absolute()
        for pin in (journal_identity, state_identity):
            if type(pin) is not tuple or len(pin) != 2 or any(type(x) is not int or x < 0 for x in pin):
                raise ValueError('INVALID_IDENTITY_PIN')
        self.journal_identity = journal_identity
        self.state_identity = state_identity

    @contextmanager
    def _locked(self):
        fd = os.open(self.state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            s = os.fstat(fd)
            if s.st_uid != os.getuid() or s.st_mode & 0o077 or _identity(s) != self.state_identity:
                raise ValueError('UNTRUSTED_GATE_DIRECTORY')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield fd
        finally:
            os.close(fd)

    def _latched(self, fd):
        try:
            os.stat(LATCH, dir_fd=fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def _latch(self, fd):
        try:
            out = os.open(LATCH, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            pass
        else:
            try:
                os.fsync(out)
            finally:
                os.close(out)
        os.fsync(fd)

    def _check_identity(self):
        s = self.path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or _identity(s) != self.journal_identity:
            raise ValueError('JOURNAL_REPLACED')

    def _run(self, operation, denied):
        with self._locked() as fd:
            if self._latched(fd):
                return denied
            try:
                self._check_identity()
                if journal.resource_snapshot(self.path)['halted']:
                    self._latch(fd)
                    return denied
                result = operation()
                self._check_identity()
                return result
            except Exception:
                self._latch(fd)
                raise

    def claim(self, job, *, now):
        return self._run(lambda: journal.claim(self.path, job, now=now), None)

    def finish(self, job, *, token, now):
        return self._run(lambda: journal.finish(self.path, job, token=token, now=now), False)

    def halt(self):
        """Persist external denial first, then halt the pinned local journal."""
        with self._locked() as fd:
            self._latch(fd)
            self._check_identity()
            journal.halt_all(self.path)
