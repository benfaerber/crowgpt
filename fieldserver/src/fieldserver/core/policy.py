"""The upload policy a recordist accepts during onboarding.

Served, not shipped in the app, so wording can be corrected without a release.
The version is what consent is recorded against: raising it makes every phone
ask again, so do that only when what happens to recordings changes, never for
a typo. The text for each version stays in the tree, since a recordist's
answers mean whatever that version said.
"""

from dataclasses import dataclass
from pathlib import Path

POLICY_DIR = Path(__file__).resolve().parents[1] / "policy"
CURRENT_VERSION = 1


@dataclass(frozen=True)
class UploadPolicy:
    version: int
    text: str

    @classmethod
    def load(cls, version: int = CURRENT_VERSION) -> "UploadPolicy":
        path = POLICY_DIR / f"upload-policy-v{version}.md"
        return cls(version=version, text=path.read_text())

    @property
    def title(self) -> str:
        first = self.text.splitlines()[0]
        return first.lstrip("# ").strip()

    def as_json(self) -> dict:
        return {"version": self.version, "title": self.title, "text": self.text}
