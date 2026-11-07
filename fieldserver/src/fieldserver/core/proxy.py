"""Trust the loopback Caddy hop, then Cloudflare only when it is that hop's peer.

Caddy MUST overwrite X-Forwarded-For with its socket peer (no trusted_proxies).
Never blindly trust two XFF entries: DNS-only clients can supply the first one.
The API binds loopback; a connection from anywhere else gets no header trust.
"""

from ipaddress import ip_address, ip_network

from werkzeug.exceptions import BadRequest
from werkzeug.middleware.proxy_fix import ProxyFix

# https://www.cloudflare.com/ips-v4/ and /ips-v6/, checked 2026-11-06.
# Review on deploy; this list grants header trust, NOT firewall access.
CLOUDFLARE_NETWORKS = tuple(map(ip_network, """
173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22
141.101.64.0/18 108.162.192.0/18 190.93.240.0/20 188.114.96.0/20
197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13
104.24.0.0/14 172.64.0.0/13 131.0.72.0/22
2400:cb00::/32 2606:4700::/32 2803:f800::/32 2405:b500::/32
2405:8100::/32 2a06:98c0::/29 2c0f:f248::/32
""".split()))


def address(value):
    try:
        return ip_address(value)
    except (ValueError, TypeError):
        return None


class CaddyCloudflareProxy:
    def __init__(self, app):
        self.app = app
        self.from_caddy = ProxyFix(self.from_edge, x_for=1, x_proto=1, x_host=1)

    def __call__(self, environ, start_response):
        if environ.get("REMOTE_ADDR") in {"127.0.0.1", "::1"}:
            return self.from_caddy(environ, start_response)
        return self.app(environ, start_response)

    def from_edge(self, environ, start_response):
        peer = address(environ.get("REMOTE_ADDR"))
        if peer and any(peer in network for network in CLOUDFLARE_NETWORKS):
            visitor = address(environ.get("HTTP_CF_CONNECTING_IP"))
            if visitor is None:
                return BadRequest("Cloudflare visitor address is missing or invalid")(
                    environ, start_response)
            environ["REMOTE_ADDR"] = str(visitor)
        return self.app(environ, start_response)
