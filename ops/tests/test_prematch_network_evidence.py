"""DNS rebinding and evidence-chain adversarial regression tests."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_pinned_transport import public_addresses, pinned_https_get
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence, verify_evidence_chain


class TestPinnedTransport(unittest.TestCase):
    def test_rejects_private_and_mixed_dns(self):
        for addresses in (["127.0.0.1"], ["8.8.8.8", "10.0.0.1"],
                          ["169.254.169.254"], ["::1"], ["fc00::1"], []):
            def resolver(*args):
                return [(2, 1, 6, "", (ip, 443)) for ip in addresses]
            with self.subTest(addresses=addresses), self.assertRaises(ValueError):
                public_addresses("api.example.test", resolver=resolver)

    def test_pins_public_ip_without_second_dns_lookup(self):
        dns_calls = []
        connections = []
        class FakeResponse:
            status = 200
            def read(self, n):
                return b"{}"
            def getheaders(self):
                return []
        class FakeConnection:
            def __init__(self, host, ip, timeout):
                connections.append((host, ip, timeout))
            def request(self, method, path, headers):
                self.headers = headers
            def getresponse(self):
                return FakeResponse()
            def close(self):
                pass
        def resolver(*args):
            dns_calls.append(1)
            return [(2, 1, 6, "", ("8.8.8.8", 443))]
        result = pinned_https_get("https://api.example.test/odds", "dummy", 2,
                                  resolver=resolver, connection_factory=FakeConnection)
        self.assertEqual(result[0], 200)
        self.assertEqual(connections, [("api.example.test", "8.8.8.8", 2)])
        self.assertEqual(len(dns_calls), 1)


class TestEvidenceChain(unittest.TestCase):
    def test_chain_replay_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            first = archive_response(b'{"one":1}', directory=directory)
            second = archive_response(b'{"two":2}', directory=directory)
            a = append_evidence(directory, first)
            b = append_evidence(directory, second)
            self.assertEqual(b["previous_hash"], a["entry_hash"])
            self.assertEqual(len(verify_evidence_chain(directory)), 2)
            ledger = Path(directory) / "evidence-ledger.jsonl"
            records = ledger.read_text().splitlines()
            changed = json.loads(records[0])
            changed["archive_sha256"] = "a" * 64
            records[0] = json.dumps(changed)
            ledger.write_text("\n".join(records) + "\n")
            with self.assertRaises(ValueError):
                verify_evidence_chain(directory)

    def test_exclusive_lock_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = archive_response(b"raw", directory=directory)
            (Path(directory) / ".evidence.lock").write_text("busy")
            with self.assertRaises(FileExistsError):
                append_evidence(directory, archive)


if __name__ == "__main__":
    unittest.main()
