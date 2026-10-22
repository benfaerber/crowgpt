"""Two embedding spaces, because neither one alone answers the question.

BIRDNET asks "is this a corvid". It is the detector that selected the training
data, so it is the right judge of content — but experiment 0014 showed it is
close to blind to audio quality. A 2 kHz lowpass kept MORE of its detections
than a neural codec that was three times closer spectrally, because BirdNET was
trained on field-archive mp3s with heavy augmentation and is deliberately invariant
to exactly the degradation we are trying to measure.

AST — a general audio transformer trained on AudioSet — has the opposite bias.
It knows nothing about crows in particular and everything about what recorded
audio sounds like, so it is sensitive to the artefacts BirdNET forgives. Phase 3
found it near chance at separating call TYPES, which is why it lost that job,
but distinguishing a real recording from a synthetic one is a different task and
the one it should be good at.

So: "robo crow" is a sentence with two halves. BirdNET can see the crow and AST
can see the robot. Reporting a Fréchet distance in both is the cheapest way to
tell which half a change improved.

Both take audio in memory rather than paths where they can, because the clips
being scored are generated and never need to touch a disk.
"""

import numpy as np

AST_SR = 16000
AST_MODEL = "MIT/ast-finetuned-audioset-10-10-0.4593"


class BirdNetEmbedder:
    """1024-d penultimate BirdNET features, the same ones Phase 3 used.

    Computed in a subprocess. Calling birdnetlib here would cost this process
    the GPU, and the AST embedder in the same run needs it.

    BirdNET returns nothing for a clip it finds no segment in, so `embed`
    comes back SHORTER than its input — 262 rows for 300 clips in 0040 —
    which is fine for distribution work (FAD) and silently wrong for
    anything joining rows back to labels. Joins use `embed_indexed`, which
    says which input rows survived; `embed` exists for the distribution
    case only.
    """

    name = "birdnet"

    def __init__(self, birdnet=None):
        self._birdnet = birdnet

    def _load(self, sample_rate):
        from crowgpt.birdnet import BirdNet

        if self._birdnet is None:
            self._birdnet = BirdNet(sample_rate=sample_rate)
        return self._birdnet

    def embed(self, clips, sample_rate):
        """Vectors only, possibly fewer rows than clips. Distributions only."""
        return self.embed_indexed(clips, sample_rate)[0]

    def embed_indexed(self, clips, sample_rate):
        """(vectors, input indices they belong to) — the join-safe form."""
        return self._load(sample_rate).embed_indexed(clips)


class AstEmbedder:
    """Mean-pooled AST hidden states — general audio, not bird-specific."""

    name = "ast"

    def __init__(self, device=None, model_id=AST_MODEL, batch_size=8):
        self.model_id = model_id
        self.batch_size = batch_size
        self._device = device
        self._model = None
        self._features = None

    def _load(self):
        if self._model is None:
            import torch
            from transformers import ASTFeatureExtractor, ASTModel

            from crowgpt.train import require_device

            self._device = self._device or require_device()
            self._features = ASTFeatureExtractor.from_pretrained(self.model_id)
            self._model = ASTModel.from_pretrained(self.model_id).to(self._device).eval()
            self._torch = torch
        return self._model

    def embed_indexed(self, clips, sample_rate):
        """One row per clip, so the indices are trivial — but a caller written
        against this interface stays correct when BirdNET is swapped in, which
        is the swap that made 0040's join silently wrong."""
        return self.embed(clips, sample_rate), list(range(len(clips)))

    def embed(self, clips, sample_rate):
        import numpy as np

        self._load()
        resampled = [_to_rate(c, sample_rate, AST_SR) for c in clips]
        out = []
        for start in range(0, len(resampled), self.batch_size):
            batch = resampled[start : start + self.batch_size]
            inputs = self._features(batch, sampling_rate=AST_SR, return_tensors="pt")
            values = inputs["input_values"].to(self._device)
            with self._torch.no_grad():
                hidden = self._model(values).last_hidden_state
            out.append(hidden.mean(dim=1).cpu().numpy())
        return np.concatenate(out).astype(np.float64) if out else np.zeros((0, 768))


def _to_rate(clip, source_rate, target_rate):
    from math import gcd

    from scipy.signal import resample_poly

    clip = np.asarray(clip, dtype=np.float32)
    if source_rate == target_rate:
        return clip
    divisor = gcd(int(source_rate), int(target_rate))
    return resample_poly(clip, target_rate // divisor, source_rate // divisor).astype(np.float32)
