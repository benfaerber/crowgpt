"""A photo in, a ranked list of corvid species out.

    identifier = PhotoIdentifier.load()
    result = identifier.identify("crow.jpg", latitude=40.76, longitude=-111.89)
    result.best.common_name, result.best.probability

The answer is the product of two terms: a logistic head over BioCLIP 2
embeddings of the whole frame and a crop of the bird, and how often each
species is recorded near where the photo was taken. Coordinates are optional
and read from the photo's EXIF when not given.

It is a closed set. The head only knows the species it was trained on, so a
photo of anything else still comes back named as one of them; `bird_box` is
None when no bird was found at all, which is the one warning it can give.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from .atlas import Atlas
from .vision import BioclipEmbedder, BirdBox, BirdDetector, PhotoFeatures, open_photo

REPO = Path(__file__).resolve().parents[2]
HEAD_FILE = "head.joblib"
ATLAS_FILE = "atlas.npz"


def default_model_dir() -> Path:
    override = os.environ.get("PHOTO_ID_MODEL")
    if override:
        return Path(override).expanduser()
    data = os.environ.get("DATA_DIR")
    base = Path(data).expanduser() if data else REPO / "data"
    return base / "photos" / "models" / "photo-id"


class ModelMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class SpeciesScore:
    slug: str
    common_name: str
    scientific_name: str
    probability: float


@dataclass(frozen=True)
class Identification:
    ranking: list
    bird_box: BirdBox | None
    used_location: bool
    #: The coordinates considered, and where they came from: "exif" for the
    #: photo's own GPS tags, "given" for the caller's, None when neither.
    latitude: float | None
    longitude: float | None
    location_source: str | None
    #: The upright frame the box is measured in.
    width: int
    height: int
    #: "corvid" when a bird was found and judged; "no_bird" when none was,
    #: and the ranking is then a guess about the whole frame; "other" when
    #: the photo is confidently of something else, named in `instead`.
    verdict: str = "corvid"
    instead: str | None = None

    @property
    def best(self) -> SpeciesScore:
        return self.ranking[0]

    def to_dict(self):
        return {
            "ranking": [vars(score) for score in self.ranking],
            "bird_box": self.bird_box.to_dict() if self.bird_box else None,
            "used_location": self.used_location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_source": self.location_source,
            "width": self.width,
            "height": self.height,
            "verdict": self.verdict,
            "instead": self.instead,
        }


class SpeciesHead:
    def __init__(self, classifier, classes):
        self.classifier = classifier
        self.classes = list(classes)

    def log_probabilities(self, vectors) -> np.ndarray:
        return np.log(self.classifier.predict_proba(np.atleast_2d(vectors)))

    def save(self, path: Path):
        joblib.dump({"classifier": self.classifier, "classes": self.classes}, path)

    @classmethod
    def load(cls, path: Path):
        stored = joblib.load(path)
        return cls(stored["classifier"], stored["classes"])


def exif_coordinates(path):
    """Latitude and longitude from a photo's GPS tags, or None."""
    from PIL import Image

    from .vision import FORMATS

    with Image.open(path, formats=FORMATS) as image:
        gps = image.getexif().get_ifd(0x8825)
    try:
        latitude = _degrees(gps[2], gps[1])
        longitude = _degrees(gps[4], gps[3])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    return latitude, longitude


def _degrees(parts, hemisphere):
    degrees, minutes, seconds = (float(p) for p in parts)
    value = degrees + minutes / 60 + seconds / 3600
    return -value if hemisphere in ("S", "W") else value


class PhotoIdentifier:
    def __init__(self, features, head: SpeciesHead, atlas: Atlas):
        self.features = features
        self.head = head
        self.atlas = atlas

    @classmethod
    def load(cls, model_dir: Path | None = None):
        model_dir = Path(model_dir) if model_dir else default_model_dir()
        if not (model_dir / HEAD_FILE).exists():
            raise ModelMissing(f"No photo model in {model_dir}. Build one with `make photo-train`.")
        features = PhotoFeatures(BirdDetector(), BioclipEmbedder())
        return cls(features, SpeciesHead.load(model_dir / HEAD_FILE), Atlas.load(model_dir / ATLAS_FILE))

    def identify(self, path, latitude=None, longitude=None, prefer_exif=False) -> Identification:
        """`prefer_exif` is for coordinates that are only a guess at where
        the photo was taken, such as the uploader's own whereabouts: the
        photo's GPS tags then win, and the guess is the fallback."""
        given = (latitude, longitude) if latitude is not None and longitude is not None else None
        tagged = exif_coordinates(path) if (prefer_exif or given is None) else None
        if tagged:
            (latitude, longitude), source = tagged, "exif"
        elif given:
            source = "given"
        else:
            latitude = longitude = source = None
        image = open_photo(path)
        vector, look = self.features.extract(image)
        verdict = "corvid" if look.box else "other" if look.instead else "no_bird"
        scores = self.head.log_probabilities(vector)[0]
        used_location = latitude is not None and self.atlas.knows(self.head.classes, latitude, longitude)
        if used_location:
            scores = scores + self.atlas.log_likelihoods(self.head.classes, latitude, longitude)
        return Identification(self._ranking(scores), look.box, used_location,
                              latitude, longitude, source, image.width, image.height,
                              verdict, look.instead)

    def _ranking(self, scores):
        probabilities = np.exp(scores - scores.max())
        probabilities = probabilities / probabilities.sum()
        ranked = sorted(zip(self.head.classes, probabilities), key=lambda pair: -pair[1])
        return [
            SpeciesScore(slug, self.atlas.names[slug]["common"], self.atlas.names[slug]["scientific"], float(p))
            for slug, p in ranked
        ]
