"""Synthetic-only unit coverage for research network-namespace ingress boundaries."""
import hashlib
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_reach_egress_boundary import (
    BrokerHold, RAW_SYNTHETIC, REQUEST, SCHEMA,
    handle_once, payload, receive, validate_response,
)


class BrokerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sock = Path(self.tmp.name) / "bridge.sock"

    def _start_server(self):
        outcomes = []
        def serve():
            try:
                outcomes.append(handle_once(self.sock))
            except Exception as exc:
                outcomes.append(type(exc).__name__)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        for _ in range(100):
            if self.sock.is_socket():
                break
            time.sleep(0.01)
        self.assertTrue(self.sock.is_socket())
        return thread, outcomes

    def test_unix_socket_synthetic_exchange_is_always_hold(self):
        thread, outcomes = self._start_server()
        result = receive(self.sock, egress_probe=lambda: False)
        thread.join(5)
        self.assertEqual(outcomes, [0])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["local_broker_transport"], "AF_UNIX")
        self.assertFalse(result["host_firewall_verified"])
        self.assertFalse(result["source_authorized"])
        self.assertFalse(result["remote_source_read"])
        self.assertFalse(result["eligible_for_model"])
        self.assertIsNone(result["verified_positive_ev"])
        self.assertFalse(result["publisher_time_attested"])
        self.assertFalse(result["raw_text_retained"])
        self.assertEqual(result["synthetic_body_sha256_only"],
                         hashlib.sha256(RAW_SYNTHETIC.encode()).hexdigest())
        self.assertNotIn("IGNORE PREVIOUS", json.dumps(result))

    def test_network_accessible_client_must_fail_before_broker_read(self):
        with self.assertRaisesRegex(BrokerHold, "DIRECT_EGRESS_IS_OPEN"):
            receive(self.sock, egress_probe=lambda: True)

    def test_missing_socket_rejected(self):
        with self.assertRaisesRegex(BrokerHold, "BROKER_SOCKET_UNAVAILABLE"):
            receive(self.sock, egress_probe=lambda: False)

    def test_wrong_request_returns_deny_and_serves_no_body(self):
        thread, outcomes = self._start_server()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(str(self.sock))
            client.sendall(b"GET https://private.example/token\n")
            answer = client.recv(512)
        thread.join(5)
        self.assertEqual(answer, b"DENIED\n")
        self.assertEqual(outcomes, ["BrokerHold"])

    def test_spoofed_origin_cannot_promote(self):
        obj = json.loads(payload())
        obj["origin_authorized"] = True
        with self.assertRaises(BrokerHold):
            validate_response((json.dumps(obj) + "\n").encode())

    def test_forged_remote_execution_cannot_promote(self):
        obj = json.loads(payload())
        obj["remote_request_executed"] = True
        with self.assertRaises(BrokerHold):
            validate_response((json.dumps(obj) + "\n").encode())

    def test_forged_timestamp_cannot_promote(self):
        obj = json.loads(payload())
        obj["upstream_time_attested"] = True
        with self.assertRaises(BrokerHold):
            validate_response((json.dumps(obj) + "\n").encode())

    def test_unexpected_source_and_schema_rejected(self):
        for changes in (
            {"source_type": "official_sports"},
            {"schema": "unknown"},
            {"body": "attacker-supplied instructions"},
            {"extra": "data"},
        ):
            with self.subTest(changes=changes):
                data = json.loads(payload())
                data.update(changes)
                with self.assertRaises(BrokerHold):
                    validate_response((json.dumps(data) + "\n").encode())

    def test_rejects_oversized_or_broken_response(self):
        for data in (b"x" * 5000, b"{not json}\n", b"{}\n", b"DENIED\n",
                     payload()[:-1], b"", "not bytes"):
            with self.subTest(value=str(data)[:50]), self.assertRaises(BrokerHold):
                validate_response(data)

    def test_stale_existing_broker_socket_or_symlink_not_overwritten(self):
        self.sock.write_text("existing file")
        with self.assertRaises(BrokerHold):
            handle_once(self.sock)
        self.assertEqual(self.sock.read_text(), "existing file")
        self.sock.unlink()
        self.sock.symlink_to(self.sock.parent / "missing")
        with self.assertRaises(BrokerHold):
            handle_once(self.sock)

    def test_only_bounded_fixed_protocol_is_issued(self):
        self.assertEqual(REQUEST, b"GET SYNTHETIC_RESEARCH_V1\n")
        self.assertNotIn(b"http", REQUEST)
        self.assertEqual(json.loads(payload())["schema"], SCHEMA)


if __name__ == "__main__":
    unittest.main()
