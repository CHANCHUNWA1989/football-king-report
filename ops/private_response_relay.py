"""Pinned standard age relay for existing private originals, not sender proof.

Only ciphertext and a separate safe receipt may be published by the workflow.
External authenticated producer/context pins are mandatory on decryption. The
module supplies no network, source authentication, durable storage or promotion.
"""
import argparse
import contextlib
import fcntl
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from ops import private_response_archive as archive
from ops import private_response_capture as capture

AGE_VERSION = 'v1.3.2'
AGE_BINARY_SHA256 = 'eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c'
MAX_CIPHERTEXT_BYTES = archive.MAX_ARCHIVE_BYTES + 100_000
SCHEMA = 'football-king-private-response-relay-v1'


class RelayError(ValueError):
    """Fixed public-safe codes, never paths, key bytes or child diagnostics."""


def _require(condition, code):
    if not condition:
        raise RelayError(code)


def _safe(function):
    @functools.wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except RelayError:
            raise
        except Exception:
            raise RelayError('PRIVATE_RELAY_OPERATION_REJECTED') from None
    return call


def _pin(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value),
             'PRIVATE_RELAY_INVALID_PIN')
    return value


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _recipient(value):
    _require(type(value) is str and re.fullmatch(r'age1pq1[023456789acdefghjklmnpqrstuvwxyz]{100,4089}', value),
             'PRIVATE_RELAY_RECIPIENT_REJECTED')
    return value


def _public_parent(path):
    """No symlink traversal; public recipient/tool may live in a checkout."""
    descriptor = os.open(path.anchor, capture.DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            _require(stat.S_ISDIR(before.st_mode), 'PRIVATE_RELAY_UNSAFE_PATH')
            child = os.open(part, capture.DIRECTORY_FLAGS, dir_fd=descriptor)
            if capture._identity(before) != capture._identity(os.fstat(child)):
                os.close(child)
                raise RelayError('PRIVATE_RELAY_UNSAFE_PATH')
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read(path, maximum, *, private):
    path = capture._path(path)
    descriptor = (capture._open_chain if private else _public_parent)(path.parent)
    try:
        if private:
            capture._directory_mode(descriptor)
            return capture._read(descriptor, path.name, maximum)
        before = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                 and before.st_uid == os.getuid() and not stat.S_IMODE(before.st_mode) & 0o022
                 and 0 < before.st_size <= maximum, 'PRIVATE_RELAY_UNSAFE_FILE')
        child = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(child, 'rb') as stream:
            _require(capture._version(before) == capture._version(os.fstat(stream.fileno())),
                     'PRIVATE_RELAY_FILE_CHANGED')
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        linked = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        _require(capture._version(before) == capture._version(after) == capture._version(linked)
                 and len(raw) == before.st_size, 'PRIVATE_RELAY_FILE_CHANGED')
        return raw
    finally:
        os.close(descriptor)


def _write(path, raw):
    path = capture._path(path)
    descriptor = capture._open_chain(path.parent)
    try:
        capture._directory_mode(descriptor)
        _require(path.name not in ('', '.', '.git'), 'PRIVATE_RELAY_UNSAFE_PATH')
        child = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=descriptor)
        with os.fdopen(child, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            before = os.fstat(stream.fileno())
        linked = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        _require(capture._version(before) == capture._version(linked)
                 and stat.S_ISREG(linked.st_mode) and linked.st_nlink == 1
                 and stat.S_IMODE(linked.st_mode) == 0o600 and linked.st_uid == os.getuid(),
                 'PRIVATE_RELAY_UNSAFE_FILE')
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def _sealed(raw, *, executable=False):
    """Immutable Linux memfd avoids path/key/binary replacement during exec."""
    descriptor = os.memfd_create('football-relay', os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(os.dup(descriptor), 'wb') as stream:
            stream.write(raw)
            stream.flush()
        os.fchmod(descriptor, 0o700 if executable else 0o600)
        # Linux UAPI values; some Python builds omit the exported constants.
        # A kernel without sealing support fails closed rather than executing.
        fcntl.fcntl(descriptor, getattr(fcntl, 'F_ADD_SEALS', 1033), 0x000F)
        yield descriptor
    finally:
        os.close(descriptor)


def _crypto(raw, arguments, age_binary, *, identity=None, maximum):
    binary = _read(age_binary, 8_000_000, private=False)
    _require(_digest(binary) == AGE_BINARY_SHA256, 'PRIVATE_RELAY_TOOL_PIN_MISMATCH')
    with contextlib.ExitStack() as stack:
        executable = stack.enter_context(_sealed(binary, executable=True))
        fds = [executable]
        command = ['/proc/self/fd/%d' % executable]
        version = subprocess.run(command + ['--version'], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 pass_fds=fds, timeout=10, check=False)
        _require(version.returncode == 0 and version.stdout.strip() == AGE_VERSION.encode(),
                 'PRIVATE_RELAY_TOOL_VERSION_MISMATCH')
        if identity is not None:
            key = stack.enter_context(_sealed(identity))
            fds.append(key)
            arguments = [*arguments, '-i', '/proc/self/fd/%d' % key]
        temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix='football-relay-private-'))
        quarantine = Path(temporary) / 'quarantine'
        fd = os.open(quarantine, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output:
            result = subprocess.run(command + arguments, input=raw, stdout=output,
                                    stderr=subprocess.DEVNULL, pass_fds=fds, timeout=90, check=False)
        # age can emit authenticated partial chunks before a late error. Nothing
        # is returned/installed unless the entire command succeeds within caps.
        _require(result.returncode == 0, 'PRIVATE_RELAY_CRYPTO_REJECTED')
        return _read(quarantine, maximum, private=True)


def _report(operation, context, manifest, archive_digest, cipher_digest, recipient_digest,
            archive_bytes, ciphertext_bytes, count):
    return {'schema': SCHEMA, 'operation': operation,
            'relay_status': 'ENCRYPTED' if operation == 'encrypt' else 'DECRYPTED_REPLAY_VERIFIED',
            **context, 'manifest_sha256': manifest, 'archive_sha256': archive_digest,
            'ciphertext_sha256': cipher_digest, 'recipient_sha256': recipient_digest,
            'archive_bytes': archive_bytes, 'ciphertext_bytes': ciphertext_bytes,
            'capture_count': count, 'encryption': 'age-v1.3.2-native-pq', **capture.FLAGS,
            'status': 'HOLD', 'certified_case_count': 0, 'eligible_for_model_scoring': False,
            'eligible_for_betting_promotion': False}


@_safe
def encrypt(private_dir, ciphertext_path, *, source_sha, run_id, attempt,
            expected_manifest_sha256, recipient, age_binary):
    context = capture._context(source_sha, run_id, attempt)
    manifest = _pin(expected_manifest_sha256)
    recipient = _recipient(recipient)
    files, count = archive._source_files(private_dir, context, manifest, None)
    raw = archive._zip(files)
    cipher = _crypto(raw, ['--encrypt', '-r', recipient], age_binary, maximum=MAX_CIPHERTEXT_BYTES)
    _write(ciphertext_path, cipher)
    return _report('encrypt', context, manifest, _digest(raw), _digest(cipher),
                   _digest(recipient.encode('ascii')), len(raw), len(cipher), count)


@_safe
def decrypt(ciphertext_path, private_dir, *, source_sha, run_id, attempt,
            expected_manifest_sha256, expected_archive_sha256, expected_ciphertext_sha256,
            expected_recipient_sha256, identity_path, age_binary):
    context = capture._context(source_sha, run_id, attempt)
    manifest, expected_archive, expected_cipher, recipient = map(_pin, (
        expected_manifest_sha256, expected_archive_sha256, expected_ciphertext_sha256,
        expected_recipient_sha256))
    cipher = _read(ciphertext_path, MAX_CIPHERTEXT_BYTES, private=True)
    _require(_digest(cipher) == expected_cipher, 'PRIVATE_RELAY_CIPHERTEXT_PIN_MISMATCH')
    identity = _read(identity_path, 8_000, private=True)
    lines = [line for line in identity.decode('ascii').splitlines() if line and not line.startswith('#')]
    _require(len(lines) == 1 and re.fullmatch('AGE-SECRET-KEY-PQ-1[A-Z0-9]{40,4096}', lines[0]),
             'PRIVATE_RELAY_IDENTITY_REJECTED')
    raw = _crypto(cipher, ['--decrypt'], age_binary, identity=identity, maximum=archive.MAX_ARCHIVE_BYTES)
    _require(_digest(raw) == expected_archive, 'PRIVATE_RELAY_ARCHIVE_PIN_MISMATCH')
    files = archive._unzip(raw)
    count = archive._validate_copy(files, context, manifest)
    _require(archive._install(private_dir, files, context, manifest) == count,
             'PRIVATE_RELAY_REPLAY_MISMATCH')
    # Recipient fingerprint is an external broker-validated pin, not a sender
    # identity or a claim derived from successfully decrypting arbitrary data.
    return _report('decrypt', context, manifest, expected_archive, expected_cipher,
                   recipient, len(raw), len(cipher), count)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RelayError('PRIVATE_RELAY_INVALID_ARGUMENTS')


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument('operation', choices=('encrypt', 'decrypt'))
        for name in ('private-dir', 'ciphertext', 'age-binary', 'identity-file',
                     'recipient-file', 'receipt-output'):
            parser.add_argument('--' + name, type=Path, required=name in ('private-dir', 'ciphertext'))
        for name in ('source-sha', 'run-id', 'attempt', 'expected-manifest-sha256',
                     'expected-archive-sha256', 'expected-ciphertext-sha256', 'expected-recipient-sha256'):
            parser.add_argument('--' + name, required=name in (
                'source-sha', 'run-id', 'attempt', 'expected-manifest-sha256'))
        args = parser.parse_args(argv)
        options = {name: getattr(args, name) for name in (
            'source_sha', 'run_id', 'attempt', 'expected_manifest_sha256')}
        options['age_binary'] = args.age_binary or Path(os.environ.get('FOOTBALL_AGE_BINARY', '/usr/local/bin/age'))
        if args.operation == 'encrypt':
            _require(args.recipient_file is not None and args.identity_file is None
                     and all(getattr(args, name) is None for name in (
                         'expected_archive_sha256', 'expected_ciphertext_sha256', 'expected_recipient_sha256')),
                     'PRIVATE_RELAY_INVALID_ARGUMENTS')
            options['recipient'] = _read(args.recipient_file, 4096, private=False).decode('ascii').strip()
            report = encrypt(args.private_dir, args.ciphertext, **options)
        else:
            _require(args.identity_file is not None and args.recipient_file is None,
                     'PRIVATE_RELAY_INVALID_ARGUMENTS')
            options.update(identity_path=args.identity_file, **{name: getattr(args, name) for name in (
                'expected_archive_sha256', 'expected_ciphertext_sha256', 'expected_recipient_sha256')})
            report = decrypt(args.ciphertext, args.private_dir, **options)
        if args.receipt_output is not None:
            _write(args.receipt_output, (json.dumps(report, sort_keys=True) + '\n').encode('ascii'))
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({'schema': SCHEMA, 'relay_status': 'REJECTED',
                          'reason': str(error) if isinstance(error, RelayError) else 'PRIVATE_RELAY_OPERATION_REJECTED',
                          'status': 'HOLD', **capture.FLAGS}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
