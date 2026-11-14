"""What the classifier sees in a photo: the whole frame and a crop of the bird.

Experiment 0092 measured the pair. A crop alone is no better than the whole
frame, because it gains the bill and loses the habitat; both together fix
small birds, the case a field photo usually is. torch and open_clip load only
when a detector or embedder is built, so the geometry here tests without them.
"""

import os
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageOps

BIOCLIP = "hf-hub:imageomics/bioclip-2"
CONFIDENT = 0.5
FAINT = 0.3
MARGIN = 1.2
THREADS = 8


#: The only decoders a photo may reach. Pillow picks a decoder from the
#: file's content, not its name, so without this a file called crow.jpg can
#: be any of the forty formats it reads.
FORMATS = ("JPEG", "PNG", "WEBP")

#: Refused before a pixel is decoded. A few megabytes of PNG can declare a
#: frame that decodes to gigabytes; the largest phone photo is about 50 MP.
MAX_PIXELS = 64_000_000

#: The longest side either model is handed. Both resize far below this, and
#: the detector's float tensor of a 50 MP frame alone is 600 MB.
MAX_SIDE = 4096


class PhotoTooLarge(ValueError):
    """The frame is larger than any camera makes, so it is not decoded."""


def open_photo(path) -> Image.Image:
    """Upright RGB. Phone photos carry their rotation in EXIF, and a sideways
    crow is not what either model was trained on."""
    with Image.open(path, formats=FORMATS) as image:
        if image.width * image.height > MAX_PIXELS:
            raise PhotoTooLarge(f"{image.width}x{image.height} is more than {MAX_PIXELS // 10**6} MP")
        upright = ImageOps.exif_transpose(image).convert("RGB")
    upright.thumbnail((MAX_SIDE, MAX_SIDE))
    return upright


@dataclass(frozen=True)
class BirdBox:
    left: float
    top: float
    right: float
    bottom: float
    score: float
    birds: int

    @classmethod
    def from_record(cls, record):
        if record is None:
            return None
        left, top, right, bottom = record["box"]
        return cls(left, top, right, bottom, record["score"], record["birds"])

    def to_record(self):
        return {"box": [self.left, self.top, self.right, self.bottom], "score": self.score, "birds": self.birds}

    def frame_share(self, image) -> float:
        return (self.right - self.left) * (self.bottom - self.top) / (image.width * image.height)

    def to_dict(self):
        return asdict(self)


def square_crop(image: Image.Image, box: BirdBox | None) -> Image.Image:
    """A square around the bird with a margin, shifted to stay inside the
    frame. The whole frame when no bird was found."""
    if box is None:
        return image
    side = min(max(box.right - box.left, box.bottom - box.top) * MARGIN, image.width, image.height)
    x = min(max((box.left + box.right) / 2 - side / 2, 0), image.width - side)
    y = min(max((box.top + box.bottom) / 2 - side / 2, 0), image.height - side)
    return image.crop((int(x), int(y), int(x + side), int(y + side)))


class BirdDetector:
    """torchvision's COCO Faster R-CNN, asked only about birds. It is fastest
    on CPU at about eight threads; more is slower."""

    def __init__(self):
        import torch
        from torchvision.models.detection import FasterRCNN_ResNet50_FPN_V2_Weights, fasterrcnn_resnet50_fpn_v2

        torch.set_num_threads(min(THREADS, len(os.sched_getaffinity(0))))
        weights = FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT
        self.model = fasterrcnn_resnet50_fpn_v2(weights=weights, box_score_thresh=FAINT).eval()
        self.bird = weights.meta["categories"].index("bird")

    def box(self, image: Image.Image) -> BirdBox | None:
        """The largest confidently detected bird, else the best faint one.
        The subject of a bird photo is usually its biggest bird."""
        import torch
        from torchvision.transforms.functional import to_tensor

        with torch.no_grad():
            found = self.model([to_tensor(image)])[0]
        birds = [(b.tolist(), s.item()) for b, label, s in zip(found["boxes"], found["labels"], found["scores"])
                 if label.item() == self.bird]
        if not birds:
            return None
        confident = [b for b in birds if b[1] >= CONFIDENT]
        if confident:
            box, score = max(confident, key=lambda b: (b[0][2] - b[0][0]) * (b[0][3] - b[0][1]))
        else:
            box, score = max(birds, key=lambda b: b[1])
        return BirdBox(*box, score, len(birds))


class BioclipEmbedder:
    """BioCLIP 2's image tower only. The text tower is a quarter of the model
    and nothing here reads it, and the stock loader holds the checkpoint and
    the model at once, 3.7 GB at its peak. Filling the image tower one tensor
    at a time from the file keeps the whole worker near 1.7 GB, which is what
    lets it run on the hosted box."""

    REPO = BIOCLIP.removeprefix("hf-hub:")
    WEIGHTS = "open_clip_model.safetensors"
    TEXT_TOWER = ("transformer", "token_embedding", "ln_final", "positional_embedding", "text_projection")

    def __init__(self):
        import open_clip

        self.model, _, self.preprocess = open_clip.create_model_and_transforms(BIOCLIP, load_weights=False)
        for name in self.TEXT_TOWER:
            delattr(self.model, name)
        self._fill_image_tower()
        self.model.eval()

    def _fill_image_tower(self):
        import torch
        from huggingface_hub import hf_hub_download
        from safetensors import safe_open

        targets = {**dict(self.model.visual.named_parameters()), **dict(self.model.visual.named_buffers())}
        with safe_open(hf_hub_download(self.REPO, self.WEIGHTS), framework="pt") as stored, torch.no_grad():
            for name, target in targets.items():
                target.copy_(stored.get_tensor(f"visual.{name}"))

    def embed(self, images) -> np.ndarray:
        import torch

        with torch.no_grad():
            vectors = self.model.encode_image(torch.stack([self.preprocess(i) for i in images]))
        return (vectors / vectors.norm(dim=-1, keepdim=True)).numpy()


class PhotoFeatures:
    """Whole-frame and bird-crop embeddings, concatenated. Training and
    identification both come through here, so they cannot drift apart."""

    def __init__(self, detector, embedder):
        self.detector = detector
        self.embedder = embedder

    def extract(self, image: Image.Image):
        box = self.detector.box(image)
        return self.vectors([(image, box)])[0], box

    def vectors(self, images_and_boxes) -> np.ndarray:
        views = [view for image, box in images_and_boxes for view in (image, square_crop(image, box))]
        embedded = self.embedder.embed(views)
        return np.hstack([embedded[0::2], embedded[1::2]])
