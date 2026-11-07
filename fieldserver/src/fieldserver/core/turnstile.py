"""Server-side verification for the public demo only, with bounded waiting."""

import json
import os
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
ACTION = "demo-generate"


class Unavailable(Exception):
    pass


@dataclass(frozen=True)
class Turnstile:
    site_key: str
    secret: str
    required: bool
    hostnames: frozenset[str] = frozenset({"crowgpt.org", "www.crowgpt.org"})

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("FIELD_TURNSTILE_SITE_KEY", ""),
                   os.environ.get("FIELD_TURNSTILE_SECRET", ""),
                   os.environ.get("FIELD_DEMO_TURNSTILE_REQUIRED") == "1")

    @property
    def configured(self):
        return bool(self.site_key and self.secret)

    def verify(self, token: str, visitor: str) -> bool:
        if not self.configured:
            raise Unavailable()
        if not token or len(token) > 2048:
            return False
        body = urlencode({"secret": self.secret, "response": token,
                          "remoteip": visitor}).encode()
        try:
            with urlopen(Request(VERIFY_URL, data=body), timeout=5) as response:
                result = json.loads(response.read(8192))
        except (URLError, TimeoutError, OSError, ValueError) as error:
            # Do not include the exception, token or secret in logs/responses.
            raise Unavailable() from error
        if not isinstance(result, dict):
            raise Unavailable()
        return (result.get("success") is True
                and result.get("hostname") in self.hostnames
                and result.get("action") == ACTION)
