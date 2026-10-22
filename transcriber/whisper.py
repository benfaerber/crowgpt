"""Speech to text, locally, on the GPU that is already in the box.

A path in, a dict out. The keys match the `dictations` transcript columns so the
caller stores what it is handed back, the same contract `analyzer/quality.measure`
documents.

THIS MODULE MUST NOT SHARE A PROCESS WITH BIRDNET. Importing birdnetlib (and
through it tflite_runtime) leaves torch permanently unable to see the GPU in that
process — `torch.cuda.is_available()` returns False forever, with no error
anywhere. `crowgpt/src/crowgpt/gpu.py` is the written record of what that cost:
an overnight run that trained on the CPU at roughly 1/240th speed while looking
merely slow. The analyze worker imports `analyzer.birdnet` at startup, which is
why transcription has a worker of its own rather than a function call in that
one. The guard below turns "silently 20x slower" into "refuses to start".
"""

import subprocess
import sys
import tempfile
from pathlib import Path

if "birdnetlib" in sys.modules or "tflite_runtime" in sys.modules:
    raise RuntimeError(
        "birdnetlib is already loaded in this process, which has permanently "
        "taken CUDA away from torch. Run the transcriber in its own process — "
        "see crowgpt/src/crowgpt/gpu.py for why winning the race is not enough.")

import torch  # noqa: E402  — deliberately after the guard
from transformers import (  # noqa: E402
    AutoProcessor,
    WhisperForConditionalGeneration,
)

#: What Whisper is trained to consume. Not a preference — the feature extractor
#: resamples anything else, so handing it 48 kHz costs time and changes nothing.
SAMPLE_RATE = 16_000

DEFAULT_MODEL = "openai/whisper-large-v3-turbo"


class NoAudioTrack(Exception):
    """The file holds no sound. Its own type for the reason analyzer's is: a
    silent file failing as a raw subprocess error says "the transcriber crashed"
    when the truth is "there is nothing here to listen to"."""


def to_wav(src: Path) -> Path:
    """Render to mono 16 kHz PCM in a temp file.

    Its own ffmpeg call rather than `analyzer.to_wav` (48 kHz, and importing
    `analyzer` risks importing birdnet) or `fieldserver.core.transcode` (no rate
    or channel arguments, and this package must not import the server).
    """
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_streams", "-select_streams", "a",
         "-of", "csv=p=0", str(src)],
        capture_output=True, text=True)
    if not probe.stdout.strip():
        raise NoAudioTrack(f"{src.name} has no audio stream")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run(
        ["ffmpeg", "-v", "quiet", "-y", "-i", str(src),
         "-ac", "1", "-ar", str(SAMPLE_RATE), tmp.name],
        check=True)
    return Path(tmp.name)


class Model:
    """Whisper, loaded once and held.

    Loading is seconds and the memo is a few, so a worker that reloaded per job
    would spend most of its life in `from_pretrained`.
    """

    def __init__(self, name: str = DEFAULT_MODEL, device: str | None = None):
        self.name = name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.processor = AutoProcessor.from_pretrained(name)
        self.model = WhisperForConditionalGeneration.from_pretrained(
            name, torch_dtype=dtype).to(self.device)
        self.model.eval()

    def transcribe(self, path: Path, language: str = "en") -> dict:
        """Return `{"text", "language", "mean_logprob", "model"}`.

        LONG-FORM IS THE WHOLE DIFFICULTY HERE, and it fails silently. Whisper's
        encoder takes exactly thirty seconds of audio. The obvious call —
        `processor(audio, return_tensors="pt")` — pads or truncates to that, so a
        ninety-second memo comes back as a fluent, confident transcript of its
        first third with no error and nothing in the output saying so. Passing
        the full-length features with an attention mask is what puts the model
        into its sequential long-form path instead.

        LANGUAGE IS FORCED, never detected. Two seconds of wind ahead of speech
        reliably detects some other language and then hallucinates fluently in
        it. `dictations.locale` records what the phone thought and is a hint to
        disagree with, not the decision.
        """
        import soundfile as sf

        audio, rate = sf.read(str(path), dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if rate != SAMPLE_RATE:
            raise ValueError(
                f"expected {SAMPLE_RATE} Hz, got {rate} — render with to_wav first")

        features = self.processor(
            audio,
            sampling_rate=SAMPLE_RATE,
            return_tensors="pt",
            # The three that turn on long-form. Without them the encoder is
            # handed a padded thirty seconds and the rest of the memo is gone.
            truncation=False,
            padding="longest",
            return_attention_mask=True,
        )
        features = features.to(self.device, self.model.dtype)

        with torch.no_grad():
            output = self.model.generate(
                **features,
                language=language,
                task="transcribe",
                return_timestamps=True,
                return_dict_in_generate=True,
                output_scores=True,
                # Whisper's own hallucination brakes. `condition_on_prev_tokens`
                # off is the important one: it is the single biggest cause of the
                # failure where the model finds a phrase it likes and repeats it
                # until the audio runs out.
                condition_on_prev_tokens=False,
                no_speech_threshold=0.6,
                compression_ratio_threshold=1.35,
                logprob_threshold=-1.0,
                temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            )

        # Long-form comes back as a dict, not a ModelOutput: passing
        # return_timestamps alongside return_dict_in_generate turns on
        # return_segments, which changes the shape without changing the type
        # annotation anywhere. Both are handled because the short path still
        # returns the object.
        sequences = output["sequences"] if isinstance(output, dict) else output.sequences
        text = self.processor.batch_decode(
            sequences, skip_special_tokens=True)[0].strip()
        return {
            "text": text,
            "language": language,
            "mean_logprob": _mean_logprob(output),
            "model": self.name,
        }


def _mean_logprob(output) -> float | None:
    """Whisper's own confidence, averaged over the decode.

    Recorded so a bad transcript is visible in the data rather than only to
    somebody who reads the words and thinks "that is not what I said".

    The long-form path reports it per segment, which is the useful one — a memo
    whose last twenty seconds were mumbled averages down and says so. Entirely
    best-effort: `generate` hands scores back in more than one shape depending on
    flags, and a missing confidence must never fail a job whose transcript is
    perfectly good.
    """
    try:
        if isinstance(output, dict) and output.get("segments"):
            # `segments` is a list per batch item; each segment carries its own
            # average log-probability.
            per_segment = [float(seg["avg_logprob"])
                           for batch in output["segments"] for seg in batch
                           if seg.get("avg_logprob") is not None]
            if per_segment:
                return sum(per_segment) / len(per_segment)
        scores = getattr(output, "sequences_scores", None)
        if scores is not None and len(scores):
            return float(scores.mean())
    except Exception:  # noqa: BLE001 — a confidence is not worth a failed job
        pass
    return None
