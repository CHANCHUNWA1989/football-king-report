"""Offline witness verifier. Caller must obtain the current pin independently."""
import hmac
import re

from intelligence_x_recovery import recover_halted


def _hex(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def _message(journal_id, generation, digest):
    if not (_hex(journal_id, 64) and type(generation) is int
            and 1 <= generation <= 2**63 - 1 and _hex(digest, 64)):
        raise ValueError('INVALID_CHECKPOINT')
    return f'intelligence-x-backup-v1\n{journal_id}\n{generation}\n{digest}\n'.encode('ascii')


def recover_witnessed(source, destination, *, checkpoint, key, expected_journal_id,
                      expected_generation, expected_digest):
    """Authenticate exact current externally pinned checkpoint; always recover halted.

    No key storage, witness service, pin acquisition, or live journal guard here.
    Never derive expected fields from the candidate backup or its checkpoint.
    """
    if type(key) is not bytes or len(key) != 32:
        raise ValueError('INVALID_WITNESS_KEY')
    _message(expected_journal_id, expected_generation, expected_digest)
    if type(checkpoint) is not dict or checkpoint.keys() != {'journal_id', 'generation', 'digest', 'mac'}:
        raise ValueError('INVALID_CHECKPOINT_FIELDS')
    jid, gen, digest, mac = (checkpoint[k] for k in ('journal_id', 'generation', 'digest', 'mac'))
    message = _message(jid, gen, digest)
    if not _hex(mac, 64) or not hmac.compare_digest(hmac.digest(key, message, 'sha256').hex(), mac):
        raise ValueError('INVALID_WITNESS_MAC')
    if (jid, gen, digest) != (expected_journal_id, expected_generation, expected_digest):
        raise ValueError('CHECKPOINT_NOT_CURRENT')
    return recover_halted(source, destination, expected_sha256=digest)
