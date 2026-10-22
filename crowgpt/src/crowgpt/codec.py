"""EnCodec as the tokenizer, and its decoder as the vocoder.

facebook/encodec_24khz runs at 75 Hz with a 320-sample hop. Bandwidth picks the
number of residual codebooks: 1.5/3/6/12/24 kbps -> 2/4/8/16/32, each 1024
entries.

Three things about this model are easy to get wrong and silent when you do.

ENCODE RETURNS A LEADING CHUNK DIMENSION. audio_codes is [n_chunks, B, K, T].
segment_length is None for the 24 kHz model so n_chunks is always 1, which makes
it tempting to squeeze it away — and then decode() rejects the shape.

THERE IS NO LOUDNESS NORMALISATION. audio_normalize is False on this model,
unlike the 48 kHz one. Archive levels vary by 30+ dB with microphone
distance, so the codec would otherwise spend codebook capacity on level. We
normalise per bout, never per call: normalising each call separately would
flatten the amplitude contour across a caw sequence, which is a real feature of
the thing being modelled.

THE ENCODER IS CAUSAL WITH AN LSTM. Codes for the same audio differ depending on
what preceded them, so a clip encoded in isolation starts from zero state and
its first frames are unreliable. Every sequence therefore carries real leading
ambience, and the same convention has to hold in the gate, in training and at
generation time or the distributions will not match.

We use transformers.EncodecModel rather than the `encodec` package: same
weights, but the package fetches them from dl.fbaipublicfiles.com through
torch.hub with no mirror, and returns a list of tuples instead of tensors.
"""

from pathlib import Path

import numpy as np
import torch

MODEL_ID = "facebook/encodec_24khz"

#: The decoder finetune's confirmed checkpoint — 0063's gate (test FAD 34.2
#: against a 30.9 raw-vs-raw floor) and Ben's ear ("no more than 10%", where
#: the frozen decoder graded D+). Pass decoder_state="finetuned" to decode
#: through it. Tokens are bit-identical either way: the encoder and quantizer
#: are always the shipped ones, so token sets, models and samplers need no
#: change — only what the tokens SOUND like moves.
FINETUNED_DECODER = (Path(__file__).resolve().parents[2] / "results"
                     / "decoder-finetune" / "adversarial" / "best.pt")
SAMPLE_RATE = 24000
HOP = 320
FRAME_RATE = 75
CODEBOOK_SIZE = 1024
BANDWIDTH_CODEBOOKS = {1.5: 2, 3.0: 4, 6.0: 8, 12.0: 16, 24.0: 32}
LEAD_FRAMES = 19  # ~0.25 s of ambience to settle the causal LSTM


class Codec:
    """Waveform <-> flat token stream."""

    def __init__(self, bandwidth=3.0, device=None, model_id=MODEL_ID, keep=None,
                 decoder_state=None):
        from transformers import EncodecModel

        from crowgpt.train import assert_on_gpu, require_device

        self.bandwidth = float(bandwidth)
        native = BANDWIDTH_CODEBOOKS[float(bandwidth)]
        # KEEP EXISTS BECAUSE THE LADDER HAS NON-NATIVE RUNGS. Bandwidth only
        # offers 2/4/8/16/32 codebooks, and 0028 needed 12 and 24 as well.
        # Truncating a higher-bandwidth encode is exact rather than approximate:
        # EnCodec's RVQ is greedy-sequential, so stage k cannot depend on a
        # later stage, and 0028 checked it — a 6 kbps encode is bit-identical to
        # the first eight rows of a 24 kbps one across every frame tested.
        if keep is not None and not 1 <= keep <= native:
            raise ValueError(f"keep must be 1..{native} at {bandwidth} kbps, got {keep}")
        self.keep = keep
        self.n_codebooks = keep or native
        # Same refusal as training, for the same reason: tokenising the corpus
        # took 2.5 hours where the GPU does it in well under one, and nothing
        # said which device it was on.
        self.device = device or require_device()
        self.model = EncodecModel.from_pretrained(model_id).to(self.device).eval()
        # DELIBERATELY OPT-IN, never automatic: an experiment measuring the
        # codec must be able to name which decoder it measured, and a silent
        # default swap would move every historical comparison at once.
        self.decoder_state = None
        if decoder_state is not None:
            path = FINETUNED_DECODER if decoder_state == "finetuned" \
                else Path(decoder_state)
            # Two formats: the finetune's own checkpoint (decoder under a
            # "decoder" key, beside optimizer state that never ships), and the
            # exported form — the decoder weights alone, as safetensors.
            if path.suffix == ".safetensors":
                from safetensors.torch import load_file

                self.model.decoder.load_state_dict(
                    load_file(str(path), device=str(self.device)))
            else:
                state = torch.load(path, map_location=self.device,
                                   weights_only=True)
                self.model.decoder.load_state_dict(state["decoder"])
            self.decoder_state = str(path)
        if self.device == "cuda":
            assert_on_gpu(self.model, "the codec")

    #: What a manifest records so a Sampler can rebuild this exact tokenizer.
    #: Bandwidth alone cannot say it any more: DAC at 24 codebooks reports a
    #: bandwidth of 18.0, which is not an EnCodec operating point at all.
    kind = "encodec-24khz"

    @property
    def vocab_size(self):
        return CODEBOOK_SIZE * self.n_codebooks

    @torch.no_grad()
    def encode(self, waveform):
        """[T] or [B, T] float in [-1, 1] -> codes [B, K, frames]."""
        batch = self._as_batch(waveform)
        encoded = self.model.encode(batch, bandwidth=self.bandwidth)
        return encoded.audio_codes[0][:, : self.n_codebooks].cpu()

    @torch.no_grad()
    def decode(self, codes):
        """codes [B, K, frames] -> waveform [B, T] float."""
        if codes.dim() == 2:
            codes = codes.unsqueeze(0)
        codes = codes.to(self.device).long()
        decoded = self.model.decode(codes.unsqueeze(0), [None])
        return decoded.audio_values.squeeze(1).cpu().numpy()

    def roundtrip(self, waveform):
        return self.decode(self.encode(waveform))

    def flatten(self, codes):
        """[K, frames] -> [frames * K] with the codebook folded into the id.

        Residual stages are unrelated to one another — code 5 in codebook 0 and
        code 5 in codebook 3 mean different things — so each gets its own slice
        of the vocabulary and therefore its own embedding.
        """
        codes = np.asarray(codes)
        offsets = (np.arange(codes.shape[0]) * CODEBOOK_SIZE)[:, None]
        return (codes + offsets).T.reshape(-1).astype(np.uint16)

    def unflatten(self, tokens):
        """[frames * K] -> [K, frames], dropping any trailing partial frame."""
        tokens = np.asarray(tokens, dtype=np.int64)
        n_frames = tokens.size // self.n_codebooks
        if n_frames == 0:
            return np.zeros((self.n_codebooks, 0), dtype=np.int64)
        grid = tokens[: n_frames * self.n_codebooks].reshape(n_frames, self.n_codebooks).T
        return grid - (np.arange(self.n_codebooks) * CODEBOOK_SIZE)[:, None]

    def _as_batch(self, waveform):
        tensor = torch.as_tensor(np.asarray(waveform), dtype=torch.float32)
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)
        return tensor.unsqueeze(1).to(self.device)


def normalise(samples, peak=0.89):
    """Peak normalise a whole bout. Never call this per unit."""
    samples = np.asarray(samples, dtype=np.float32)
    loudest = float(np.max(np.abs(samples)))
    if loudest <= 0:
        return samples
    return samples / loudest * peak
