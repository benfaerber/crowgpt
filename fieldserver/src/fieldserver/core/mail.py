"""Outbound mail, for the one message this server sends: an invite.

Cloudflare Email Routing receives for crowgpt.org and cannot send, so sending
goes through Resend's HTTP API — one POST, no SMTP, no library. It is optional:
without RESEND_API_KEY in the environment `Mailer.from_env()` is None and an
approval produces a link for Ben to pass on by hand instead of an email. Set
FIELD_MAIL_FROM to the verified sender; the domain has to carry Resend's DNS
records before it will accept it.
"""

import json
import os
import urllib.error
import urllib.request

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "CrowGPT <hello@crowgpt.org>"


class Mailer:
    def __init__(self, api_key: str, sender: str = DEFAULT_FROM, timeout: float = 15.0):
        self.api_key = api_key
        self.sender = sender
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        key = os.environ.get("RESEND_API_KEY")
        if not key:
            return None
        return cls(key, os.environ.get("FIELD_MAIL_FROM") or DEFAULT_FROM)

    def send(self, to: str, subject: str, text: str) -> None:
        """Deliver, or raise with the provider's reason."""
        body = json.dumps({"from": self.sender, "to": [to], "subject": subject,
                           "text": text}).encode()
        request = urllib.request.Request(
            RESEND_URL, data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status >= 300:
                    raise RuntimeError(f"mail provider answered {response.status}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:200]
            raise RuntimeError(f"mail provider refused ({error.code}): {detail}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"mail provider unreachable: {error.reason}") from error
