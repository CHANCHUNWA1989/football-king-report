"""Pinned public-IP HTTPS transport to avoid DNS rebinding between validation and connect."""
import http.client
import ipaddress
import socket
import ssl
import urllib.parse


def public_addresses(host, *, resolver=socket.getaddrinfo):
    answers = resolver(host, 443, 0, socket.SOCK_STREAM)
    addresses = []
    for entry in answers:
        address = ipaddress.ip_address(entry[4][0])
        if not address.is_global:
            raise ValueError("non-public DNS address")
        if str(address) not in addresses:
            addresses.append(str(address))
    if not addresses:
        raise ValueError("no DNS answers")
    return addresses


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, *, timeout):
        super().__init__(host, port=443, timeout=timeout,
                         context=ssl.create_default_context())
        self._pinned_ip = ip

    def connect(self):
        # TLS hostname verification and SNI still use the original DNS name.
        sock = socket.create_connection((self._pinned_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def pinned_https_get(url, secret, timeout_seconds, *, resolver=socket.getaddrinfo,
                     connection_factory=_PinnedHTTPS, max_bytes=1_000_000):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
        raise ValueError("invalid HTTPS endpoint")
    addresses = public_addresses(parsed.hostname, resolver=resolver)
    # Never re-resolve the hostname inside the connection. TLS verifies DNS name.
    connection = connection_factory(parsed.hostname, addresses[0], timeout=timeout_seconds)
    try:
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection.request("GET", path, headers={
            "Authorization": "Bearer " + secret, "Accept": "application/json",
            "Host": parsed.hostname, "Connection": "close"})
        response = connection.getresponse()
        body = response.read(max_bytes + 1)
        return response.status, body, dict(response.getheaders())
    finally:
        connection.close()
