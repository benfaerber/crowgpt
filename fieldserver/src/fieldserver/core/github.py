"""Sign in with GitHub, for the operator dashboard only.

A convenience beside the operator token, not a replacement: typing a 32-char
secret on a phone is the thing it saves. Who may get in is a list of numeric
GitHub user ids, never logins — a login can be renamed and then claimed by a
stranger, an id cannot.

Off unless all three variables are set. FIELD_GITHUB_CLIENT_ID and
FIELD_GITHUB_CLIENT_SECRET come from an OAuth App whose callback URL is
<server>/api/operator/github/callback; FIELD_GITHUB_OPERATORS is a comma list
of ids (`gh api user --jq .id`).
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .mail import USER_AGENT

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"


class GitHubRefused(Exception):
    """GitHub would not say who this is."""


class GitHubSignIn:
    def __init__(self, client_id: str, client_secret: str, operators: set[int],
                 timeout: float = 15.0):
        self.client_id = client_id
        self.client_secret = client_secret
        self.operators = operators
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        client_id = os.environ.get("FIELD_GITHUB_CLIENT_ID")
        client_secret = os.environ.get("FIELD_GITHUB_CLIENT_SECRET")
        operators = {int(part) for part in
                     (os.environ.get("FIELD_GITHUB_OPERATORS") or "").split(",")
                     if part.strip().isdigit()}
        if not (client_id and client_secret and operators):
            return None
        return cls(client_id, client_secret, operators)

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        return AUTHORIZE_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "allow_signup": "false",
        })

    def admits(self, user: dict) -> bool:
        return user.get("id") in self.operators

    def identify(self, code: str, redirect_uri: str) -> dict:
        """The GitHub user who just approved, as GitHub describes them."""
        grant = self._call(TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        })
        access_token = grant.get("access_token")
        if not access_token:
            raise GitHubRefused(grant.get("error_description") or grant.get("error")
                                or "no access token")
        return self._call(USER_URL, bearer=access_token)

    def _call(self, url: str, data: dict | None = None, bearer: str | None = None) -> dict:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        request = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise GitHubRefused(f"GitHub answered {error.code}") from error
        except urllib.error.URLError as error:
            raise GitHubRefused(f"GitHub unreachable: {error.reason}") from error
