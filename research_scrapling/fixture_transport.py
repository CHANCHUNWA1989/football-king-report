"""Bounded synthetic HTTP-like wire protocol on a connected Unix socket only.
No listener, proxy, DNS, IP socket or real provider. The client MUST half-close
its write side; one frame per connection. Not a general HTTP implementation.
"""
import socket
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from egress_contract import request

MAX_FRAME = 4096
DENIED = b'HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'


def dispatch(domain, frame):
    if type(frame) is not bytes or not 0 < len(frame) <= MAX_FRAME:
        raise ValueError('invalid frame size')
    if not frame.endswith(b'\r\n\r\n') or frame.count(b'\r\n\r\n') != 1:
        raise ValueError('invalid framing')
    lines = frame[:-4].decode('ascii').split('\r\n')
    if len(lines) != 4:
        raise ValueError('invalid header count')
    parts = lines[0].split(' ')
    if len(parts) != 3 or parts[2] != 'HTTP/1.1':
        raise ValueError('invalid request line')
    if lines[1:] != ['Host: fixture.invalid', 'Accept: application/octet-stream', 'Connection: close']:
        raise ValueError('invalid headers')
    result = request(domain, parts[0], parts[1], {'accept':'application/octet-stream'}, b'')
    if (result['synthetic_only'] is not True or result['model_input_allowed'] is not False
            or result['status'] != 'HOLD' or result['network_rehearsal_allowed'] is not False
            or result['live_trading'] != 'DISABLED' or result['production_recommendations'] != 'DISABLED'):
        raise ValueError('unsafe fixture result')
    body = result['body']
    return (b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Type: application/octet-stream\r\nContent-Length: '
            + str(len(body)).encode('ascii') + b'\r\n\r\n' + body)


def serve_once(domain, peer):
    """Own and close one connected AF_UNIX stream. No automatic retry."""
    with peer:
        if peer.family != socket.AF_UNIX or peer.type != socket.SOCK_STREAM:
            raise ValueError('Unix stream required')
        deadline = time.monotonic() + 2
        frame = bytearray()
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('frame deadline exceeded')
                peer.settimeout(remaining)
                chunk = peer.recv(min(1024, MAX_FRAME+1-len(frame)))
                if not chunk:
                    break
                frame.extend(chunk)
                if len(frame) > MAX_FRAME:
                    raise ValueError('frame exceeds limit')
            response = dispatch(domain, bytes(frame))
        except (ValueError, OSError):
            response = DENIED
        peer.settimeout(1)
        peer.sendall(response)


class Tests(unittest.TestCase):
    good = (b'GET /fixture/league-history HTTP/1.1\r\nHost: fixture.invalid\r\n'
            b'Accept: application/octet-stream\r\nConnection: close\r\n\r\n')

    def exchange(self, frame, domain='football'):
        a,b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        with a, ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(serve_once, domain, b)
            a.settimeout(4)
            a.sendall(frame)
            a.shutdown(socket.SHUT_WR)
            data = bytearray()
            while chunk := a.recv(4096):
                data.extend(chunk)
            future.result(timeout=4)
            return bytes(data)

    def test_actual_unix_roundtrip(self):
        self.assertTrue(self.exchange(self.good).endswith(b'synthetic-league-fixture'))

    def test_quant_roundtrip(self):
        self.assertTrue(self.exchange(self.good.replace(b'league-history', b'fx-reference'), 'quant').endswith(b'synthetic-fx-fixture'))

    def test_cross_domain(self):
        self.assertEqual(self.exchange(self.good, 'quant'), DENIED)

    def test_duplicate_host_and_length(self):
        for h in (b'Host: other.invalid',b'Content-Length: 0',b'Transfer-Encoding: chunked'):
            self.assertEqual(self.exchange(self.good.replace(b'Connection: close', h+b'\r\nConnection: close')), DENIED)

    def test_pipelining_and_body(self):
        for frame in (self.good+self.good,self.good+b'x', self.good[:-1]):
            self.assertEqual(self.exchange(frame), DENIED)

    def test_arbitrary_destination(self):
        for dest in (b'https://example.invalid/',b'//example.invalid/',b'/fixture/%6ceague-history',b'/fixture/league-history?x=1'):
            self.assertEqual(self.exchange(self.good.replace(b'/fixture/league-history', dest)), DENIED)

    def test_method_version_and_host(self):
        for frame in (self.good.replace(b'GET ',b'CONNECT '), self.good.replace(b'HTTP/1.1',b'HTTP/1.0'), self.good.replace(b'fixture.invalid',b'other.invalid')):
            self.assertEqual(self.exchange(frame), DENIED)

    def test_oversize_and_non_ascii(self):
        self.assertEqual(self.exchange(b'x'*(MAX_FRAME+1)), DENIED)
        self.assertEqual(self.exchange(self.good.replace(b'GET',b'G\xffT')), DENIED)

    def test_missing_half_close(self):
        a,b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        with a, ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(serve_once, 'football', b)
            a.settimeout(4)
            a.sendall(self.good)
            self.assertEqual(a.recv(4096), DENIED)
            future.result(timeout=4)

    def test_no_ip_socket_accepted(self):
        with self.assertRaises(ValueError):
            serve_once('football', socket.socket(socket.AF_INET, socket.SOCK_STREAM))


if __name__ == '__main__':
    unittest.main(verbosity=2)
