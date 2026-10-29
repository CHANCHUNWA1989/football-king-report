"""Synthetic archive tests for the fixed official age installer; no network."""
import hashlib
import importlib
import io
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tar_bytes(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, raw, kind in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            if kind == tarfile.REGTYPE:
                info.size = len(raw)
            elif kind == tarfile.SYMTYPE:
                info.linkname = '/outside-target'
            archive.addfile(info, io.BytesIO(raw) if kind == tarfile.REGTYPE else None)
    return output.getvalue()


class Response(io.BytesIO):
    def geturl(self):
        return 'https://release-assets.githubusercontent.com/synthetic-unit-fixture'


class InstallAgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.destination = self.root / 'age-tool'
        self.entries = [('age', b'', tarfile.DIRTYPE),
                        ('age/age', b'synthetic-age-only', tarfile.REGTYPE),
                        ('age/age-keygen', b'synthetic-keygen-only', tarfile.REGTYPE)]
        self.raw = tar_bytes(self.entries)
        self.calls = []

    def module(self):
        return importlib.import_module('ops.install_age')

    def constants(self, raw=None):
        module = self.module()
        return patch.multiple(module, ARCHIVE_BYTES=len(self.raw if raw is None else raw),
                              ARCHIVE_SHA256=digest(self.raw if raw is None else raw),
                              ALLOWED_MEMBERS={name: len(body) for name, body, _ in self.entries},
                              BINARY_HASHES={Path(name).name: digest(body)
                                             for name, body, kind in self.entries if kind == tarfile.REGTYPE})

    def opener(self, request, *, timeout):
        self.calls.append(request)
        self.assertEqual(request.full_url, self.module().URL)
        self.assertEqual(timeout, 30)
        self.assertIsNone(request.get_header('Authorization'))
        self.assertIsNone(request.get_header('Cookie'))
        return Response(self.raw)

    def test_exact_pinned_install_and_private_reuse_without_network(self):
        with self.constants():
            report = self.module().install(self.destination, opener=self.opener)
            self.assertFalse(report['reused'])
            self.assertEqual(len(self.calls), 1)
            self.assertEqual(set(p.name for p in self.destination.iterdir()), {'age', 'age-keygen'})
            self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o700)
            for name in ('age', 'age-keygen'):
                path = self.destination / name
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
                self.assertEqual(digest(path.read_bytes()), self.module().BINARY_HASHES[name])
            reused = self.module().install(self.destination,
                opener=lambda *a, **k: self.fail('reusing pinned install must not download'))
            self.assertTrue(reused['reused'])
            self.assertFalse(report['sigsum_proof_verified'])

    def test_size_and_digest_fail_before_destination_is_created(self):
        for raw in (self.raw + b'x', self.raw[:-1], self.raw[:-1] + bytes([self.raw[-1] ^ 1])):
            with self.subTest(size=len(raw)), self.constants():
                with self.assertRaises(ValueError):
                    self.module().install(self.destination, opener=lambda *a, **k: Response(raw))
                self.assertFalse(self.destination.exists())

    def test_tar_extra_traversal_duplicate_and_symlink_are_rejected_even_with_matching_outer_hash(self):
        malformed = [self.entries + [('age/extra', b'x', tarfile.REGTYPE)],
                     self.entries + [('../outside', b'x', tarfile.REGTYPE)],
                     self.entries + [self.entries[1]],
                     [self.entries[0], ('age/age', b'', tarfile.SYMTYPE), self.entries[2]]]
        for entries in malformed:
            raw = tar_bytes(entries)
            with self.subTest(entries=[entry[0] for entry in entries]), self.constants(raw):
                with self.assertRaises(ValueError):
                    self.module().install(self.destination, opener=lambda *a, **k: Response(raw))
                self.assertFalse(self.destination.exists())

    def test_binary_hash_is_checked_separately_from_valid_outer_archive(self):
        entries = [self.entries[0], ('age/age', b'X' * len(self.entries[1][1]), tarfile.REGTYPE), self.entries[2]]
        raw = tar_bytes(entries)
        with self.constants(raw), self.assertRaisesRegex(ValueError, '^AGE_BINARY_DIGEST_MISMATCH$'):
            self.module().install(self.destination, opener=lambda *a, **k: Response(raw))
        self.assertFalse(self.destination.exists())

    def test_existing_bad_mode_or_changed_binary_is_never_overwritten(self):
        with self.constants():
            self.module().install(self.destination, opener=self.opener)
            changed = self.destination / 'age'
            changed.write_bytes(b'changed-synthetic-tool')
            with self.assertRaises(ValueError):
                self.module().install(self.destination, opener=lambda *a, **k: self.fail('must not download'))
            self.assertEqual(changed.read_bytes(), b'changed-synthetic-tool')
            changed.write_bytes(self.entries[1][1])
            self.destination.chmod(0o755)
            with self.assertRaises(ValueError):
                self.module().install(self.destination, opener=lambda *a, **k: self.fail('must not download'))

    def test_symlink_hardlink_and_repository_destinations_fail_closed(self):
        with self.constants():
            other = self.root / 'other'
            other.mkdir(mode=0o700)
            self.destination.symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.module().install(self.destination, opener=self.opener)
            self.destination.unlink()
            self.module().install(self.destination, opener=self.opener)
            os.link(self.destination / 'age', self.root / 'hardlink')
            with self.assertRaises(ValueError):
                self.module().install(self.destination, opener=self.opener)
            repo = self.root / 'repository'
            repo.mkdir()
            (repo / '.git').mkdir()
            with self.assertRaises(ValueError):
                self.module().install(repo / 'age', opener=self.opener)

    def test_network_error_text_is_not_exposed(self):
        def bad_opener(*args, **kwargs):
            raise OSError('synthetic-private-proxy-error-never-display')
        with self.constants(), self.assertRaisesRegex(ValueError, '^AGE_INSTALL_REJECTED$') as error:
            self.module().install(self.destination, opener=bad_opener)
        self.assertNotIn('synthetic-private-proxy', str(error.exception))
        self.assertFalse(self.destination.exists())


if __name__ == '__main__':
    unittest.main()
