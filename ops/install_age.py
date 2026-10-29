"""Install exactly pinned official age v1.3.2 Linux/amd64 tools.

Only the official HTTPS asset and its published GitHub release digest are used.
This installer does not verify the separate Sigsum proof or authenticate football
sources. It installs no plugins and never reads credentials or executes a shell.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tarfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from ops import private_response_capture as capture


VERSION = 'v1.3.2'
URL = 'https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz'
ARCHIVE_BYTES = 19_405_817
ARCHIVE_SHA256 = 'cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10'
BINARY_HASHES = {
    'age': 'eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c',
    'age-keygen': '0a0009db842259d6717f7eeb30acb6b90d2a2eb924c6acd0a0db0ca1f1537899',
}
ALLOWED_MEMBERS = {
    'age': 0,
    'age/age-keygen': 4_051_278,
    'age/age-plugin-tag': 4_276_743,
    'age/age-plugin-batchpass': 4_224_528,
    'age/age-plugin-pq': 4_339_590,
    'age/age-plugin-tagpq': 4_291_077,
    'age/age': 6_977_014,
    'age/LICENSE': 2_975,
    'age/age-inspect': 4_511_789,
}
MAX_BINARY_BYTES = 10_000_000
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class InstallError(ValueError):
    """Fixed, public-safe failure codes only."""


def _require(condition, code):
    if not condition:
        raise InstallError(code)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _download(opener):
    request = Request(URL, headers={'User-Agent': 'football-king-pinned-age-installer',
                                    'Accept': 'application/octet-stream'})
    with opener(request, timeout=30) as response:
        final = urlsplit(response.geturl())
        _require(final.scheme == 'https' and final.username is None and final.password is None
                 and final.hostname in {'github.com', 'objects.githubusercontent.com',
                                        'release-assets.githubusercontent.com'}
                 and getattr(response, 'status', 200) == 200,
                 'AGE_DOWNLOAD_RESPONSE_REJECTED')
        raw = response.read(ARCHIVE_BYTES + 1)
    _require(type(raw) is bytes and len(raw) == ARCHIVE_BYTES, 'AGE_ARCHIVE_SIZE_MISMATCH')
    _require(_digest(raw) == ARCHIVE_SHA256, 'AGE_ARCHIVE_DIGEST_MISMATCH')
    return raw


def _unpack(raw):
    binaries, seen = {}, set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            _require(member.name in ALLOWED_MEMBERS and member.name not in seen
                     and len(seen) < len(ALLOWED_MEMBERS)
                     and member.size == ALLOWED_MEMBERS[member.name]
                     and not member.issym() and not member.islnk()
                     and not member.sparse and not member.pax_headers,
                     'AGE_ARCHIVE_LAYOUT_REJECTED')
            seen.add(member.name)
            _require(member.isdir() if member.name == 'age' else member.isreg(),
                     'AGE_ARCHIVE_LAYOUT_REJECTED')
            name = member.name.removeprefix('age/')
            if member.name.startswith('age/') and name in BINARY_HASHES:
                _require(0 < member.size <= MAX_BINARY_BYTES, 'AGE_BINARY_SIZE_REJECTED')
                with archive.extractfile(member) as stream:
                    body = stream.read(MAX_BINARY_BYTES + 1)
                _require(len(body) == member.size and _digest(body) == BINARY_HASHES[name],
                         'AGE_BINARY_DIGEST_MISMATCH')
                binaries[name] = body
    _require(seen == set(ALLOWED_MEMBERS) and set(binaries) == set(BINARY_HASHES),
             'AGE_ARCHIVE_LAYOUT_REJECTED')
    return binaries


def _open_destination(parent, name):
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    _require(stat.S_ISDIR(before.st_mode), 'AGE_DESTINATION_REJECTED')
    descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
    try:
        _require(capture._identity(before) == capture._identity(os.fstat(descriptor)),
                 'AGE_DESTINATION_CHANGED')
        capture._directory_mode(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _verify(parent, name, descriptor):
    capture._directory_mode(descriptor)
    _require(set(os.listdir(descriptor)) == set(BINARY_HASHES), 'AGE_DESTINATION_CONTENTS_REJECTED')
    for binary, expected in BINARY_HASHES.items():
        before = os.stat(binary, dir_fd=descriptor, follow_symlinks=False)
        _require(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o700
                 and before.st_uid == os.getuid() and before.st_nlink == 1
                 and 0 < before.st_size <= MAX_BINARY_BYTES, 'AGE_INSTALLED_FILE_REJECTED')
        child = os.open(binary, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(child, 'rb') as stream:
            _require(capture._version(before) == capture._version(os.fstat(stream.fileno())),
                     'AGE_INSTALLED_FILE_CHANGED')
            raw = stream.read(MAX_BINARY_BYTES + 1)
            after = os.fstat(stream.fileno())
        linked = os.stat(binary, dir_fd=descriptor, follow_symlinks=False)
        _require(capture._version(before) == capture._version(after) == capture._version(linked)
                 and _digest(raw) == expected, 'AGE_INSTALLED_FILE_CHANGED')
    _require(capture._identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
             == capture._identity(os.fstat(descriptor)), 'AGE_DESTINATION_CHANGED')


def _report(reused):
    return {'schema': 'football-king-pinned-age-install-v1', 'age_version': VERSION,
            'installed': True, 'reused': reused, 'archive_sha256': ARCHIVE_SHA256,
            'binary_sha256': dict(BINARY_HASHES), 'sigsum_proof_verified': False}


def install(destination, *, opener=None):
    """Install outside Git into a new 0700 directory or verify exact pinned reuse.

    The caller must supply an existing controlled parent. Failed installations
    never overwrite existing entries; an interrupted partial directory is rejected
    on reuse and may be removed with the disposable runner workspace.
    """
    parent = descriptor = None
    try:
        _require(sys.platform == 'linux' and platform.machine() in ('x86_64', 'amd64'),
                 'AGE_PLATFORM_UNSUPPORTED')
        destination = capture._path(destination)
        _require(destination.name not in ('', '.', '..'), 'AGE_DESTINATION_REJECTED')
        parent = capture._open_chain(destination.parent)
        try:
            os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            descriptor = _open_destination(parent, destination.name)
            _verify(parent, destination.name, descriptor)
            return _report(True)
        binaries = _unpack(_download(urlopen if opener is None else opener))
        os.mkdir(destination.name, 0o700, dir_fd=parent)
        descriptor = _open_destination(parent, destination.name)
        for name, raw in binaries.items():
            child = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o700, dir_fd=descriptor)
            with os.fdopen(child, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        _verify(parent, destination.name, descriptor)
        return _report(False)
    except InstallError:
        raise
    except Exception:
        raise InstallError('AGE_INSTALL_REJECTED') from None
    finally:
        for opened in (descriptor, parent):
            if opened is not None:
                os.close(opened)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InstallError('AGE_INSTALL_ARGUMENTS_REJECTED')


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument('--destination', required=True)
        args = parser.parse_args(argv)
        print(json.dumps(install(Path(args.destination)), sort_keys=True))
        return 0
    except InstallError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
