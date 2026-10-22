"""DAC as a drop-in alternative tokenizer, for the one comparison that is fair.

WHY THIS IS WORTH TRYING, in one number. Experiment 0014 measured EnCodec's
codebook entropy on crow audio at 7.40 bits of a possible 10 — a quarter of the
codec's representational capacity unused, with the first and most important
codebook down at 6.3. Fixing exactly that collapse, via factorised and
L2-normalised codes, is what the DAC paper is about, and DAC was trained on
environmental audio as well as speech and music, where a corvid is less of an
outlier.

WHY THE COMPARISON IS CLEAN. DAC's 24 kHz model has the same geometry as
EnCodec's: 24 kHz in, hop 320, 75 frames per second, 1024 entries per codebook.
Taking 8 of its 32 codebooks gives the same bitrate, the same frame rate and the
SAME SEQUENCE LENGTH as the EnCodec setup in use. Nothing about the modelling
problem changes, so any difference is the codec.

That is the property 12 kbps lacked. It raised the ceiling by doubling the
codebooks, and the model lost more to the harder sequence than the ceiling gave
back — 56% of ceiling against 96%. DAC aims to raise the ceiling at constant
sequence length, which is the only version of this trade that can pay.
"""

import numpy as np
import torch

from crowgpt.codec import CODEBOOK_SIZE

SAMPLE_RATE = 24000
MODEL_TYPE = "24khz"


class DacCodec:
    """Same interface as crowgpt.codec.Codec, backed by DAC.

    `n_codebooks` selects how many residual stages to keep, which is DAC's
    bitrate knob: 8 stages at 75 Hz and 10 bits is 6 kbps, matching the EnCodec
    setting it is being compared against.
    """

    def __init__(self, n_codebooks=8, device=None, model_type=MODEL_TYPE):
        import dac

        from crowgpt.train import require_device

        self.device = device or require_device()
        self.n_codebooks = int(n_codebooks)
        self.model = dac.DAC.load(dac.utils.download(model_type=model_type))
        self.model = self.model.to(self.device).eval()
        if self.n_codebooks > self.model.n_codebooks:
            raise ValueError(
                f"asked for {self.n_codebooks} codebooks, DAC {model_type} has "
                f"{self.model.n_codebooks}"
            )
        self.sample_rate = self.model.sample_rate
        self.kind = f"dac-{model_type}"
        self.bandwidth = self.n_codebooks * 0.75  # 10 bits x 75 Hz per stage

    @property
    def vocab_size(self):
        return CODEBOOK_SIZE * self.n_codebooks

    @torch.no_grad()
    def encode(self, waveform):
        """[T] or [B, T] float -> codes [B, K, frames], K = n_codebooks."""
        batch = self._as_batch(waveform)
        # DAC pads to a multiple of the hop itself; preprocess also handles the
        # rate check, so a mismatched input fails loudly rather than resampling
        # silently behind our back.
        prepared = self.model.preprocess(batch, self.sample_rate)
        _, codes, _, _, _ = self.model.encode(prepared, n_quantizers=self.n_codebooks)
        return codes[:, : self.n_codebooks, :].cpu()

    @torch.no_grad()
    def decode(self, codes):
        """codes [B, K, frames] -> waveform [B, T] float."""
        if codes.dim() == 2:
            codes = codes.unsqueeze(0)
        codes = codes.to(self.device).long()
        if codes.shape[1] < self.model.n_codebooks:
            # from_codes wants every stage; the ones we dropped contribute
            # nothing, and zero is the code that says so.
            pad = torch.zeros(
                codes.shape[0], self.model.n_codebooks - codes.shape[1], codes.shape[2],
                dtype=torch.long, device=self.device,
            )
            codes = torch.cat([codes, pad], dim=1)
        latents, _, _ = self.model.quantizer.from_codes(codes)
        return self.model.decode(latents).squeeze(1).cpu().numpy()

    def roundtrip(self, waveform):
        return self.decode(self.encode(waveform))

    def flatten(self, codes):
        codes = np.asarray(codes)
        offsets = (np.arange(codes.shape[0]) * CODEBOOK_SIZE)[:, None]
        return (codes + offsets).T.reshape(-1).astype(np.uint16)

    def unflatten(self, tokens):
        tokens = np.asarray(tokens, dtype=np.int64)
        frames = tokens.size // self.n_codebooks
        if frames == 0:
            return np.zeros((self.n_codebooks, 0), dtype=np.int64)
        grid = tokens[: frames * self.n_codebooks].reshape(frames, self.n_codebooks).T
        return grid - (np.arange(self.n_codebooks) * CODEBOOK_SIZE)[:, None]

    def _as_batch(self, waveform):
        tensor = torch.as_tensor(np.asarray(waveform), dtype=torch.float32)
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)
        return tensor.unsqueeze(1).to(self.device)


class Resampled:
    """A codec that runs at a different rate than the corpus does.

    EXISTS BECAUSE THE 44 kHz MODEL DOES NOT RESAMPLE AND DOES NOT SAY SO.
    `DacCodec.encode` hands the model `self.sample_rate` and DAC's preprocess
    trusts it, so passing 24 kHz audio to the 44 kHz model REINTERPRETS it —
    a 3-second caw becomes 1.63 seconds, pitched up by 1.84x — and every stage
    downstream looks like it worked. 0033 caught it only because the decoded
    clips came back the wrong length.

    So the resampling lives in the codec rather than in each caller. Anything
    holding one of these can keep thinking in corpus samples: audio goes in at
    `source_rate`, tokens come out, and decoded audio comes back at
    `source_rate` with the same duration it went in with.

    `kind` carries the source rate so a manifest can rebuild the pair. A token
    set written through a resampling codec and read back without one would
    decode at the wrong rate, which is audible but easy to blame on the model.
    """

    def __init__(self, inner, source_rate):
        self.inner = inner
        self.source_rate = int(source_rate)
        self.n_codebooks = inner.n_codebooks
        self.bandwidth = inner.bandwidth
        self.sample_rate = self.source_rate
        self.kind = f"{inner.kind}@{self.source_rate}"

    @property
    def vocab_size(self):
        return self.inner.vocab_size

    def _to(self, x, source, target):
        from scipy.signal import resample_poly

        if source == target:
            return np.asarray(x, dtype=np.float32)
        g = np.gcd(int(source), int(target))
        return resample_poly(x, int(target) // g, int(source) // g, axis=-1).astype(np.float32)

    def encode(self, waveform):
        return self.inner.encode(self._to(np.asarray(waveform), self.source_rate,
                                          self.inner.sample_rate))

    def decode(self, codes):
        return self._to(self.inner.decode(codes), self.inner.sample_rate, self.source_rate)

    def roundtrip(self, waveform):
        return self.decode(self.encode(waveform))

    def flatten(self, codes):
        return self.inner.flatten(codes)

    def unflatten(self, tokens):
        return self.inner.unflatten(tokens)


class Delayed:
    """MusicGen's delay pattern over any codec's flat stream.

    THE FLAT LAYOUT IS THE ONE THING NEVER VARIED. Every model in this project
    predicts codebook k of frame t from codebooks 0..k-1 of the SAME frame plus
    everything before it, so the fine stages are chained to a coarse prediction
    made three tokens earlier and errors compound inside a frame. MusicGen
    reports flat interleaving as the worst of its four layouts and the delay
    pattern as the fix.

    Stage k carries frame t-k, so at every position the model is predicting one
    stage of one frame with a *full frame* of history behind it rather than a
    few tokens of the same frame.

    EDGE-CLAMPED RATHER THAN PADDED, which is what keeps this cheap. The obvious
    implementation adds a PAD id for the head of the stream, and that costs a
    vocabulary entry, a change to `Vocabulary.allowed`, a change to `LegalMask`,
    and a new way for generation to emit something illegal. Clamping the head to
    frame 0 instead means the stream stays exactly K-periodic with the same
    vocabulary and the same mask — nothing downstream knows this happened.

    The arithmetic, because it is easy to get backwards:

        flatten:    block i, stage k  <-  codes[k][max(0, i - k)]
        unflatten:  frame t, stage k  <-  block (t + k), stage k

    So F frames need F + K - 1 blocks, and a 3-second bout at eight codebooks
    grows from 1,800 tokens to 1,856 — 3%, against a 4,096 block.
    """

    def __init__(self, inner):
        self.inner = inner
        self.n_codebooks = inner.n_codebooks
        self.bandwidth = inner.bandwidth
        self.sample_rate = getattr(inner, "sample_rate", 24000)
        self.kind = f"{inner.kind}+delay"

    @property
    def vocab_size(self):
        return self.inner.vocab_size

    def encode(self, waveform):
        return self.inner.encode(waveform)

    def decode(self, codes):
        return self.inner.decode(codes)

    def roundtrip(self, waveform):
        return self.decode(self.unflatten(self.flatten(self.encode(waveform)[0])))

    def flatten(self, codes):
        codes = np.asarray(codes)
        stages, frames = codes.shape
        blocks = frames + stages - 1
        grid = np.empty((stages, blocks), dtype=np.int64)
        for k in range(stages):
            source = np.clip(np.arange(blocks) - k, 0, frames - 1)
            grid[k] = codes[k][source]
        return self.inner.flatten(grid)

    def unflatten(self, tokens):
        grid = self.inner.unflatten(tokens)
        stages, blocks = grid.shape
        frames = blocks - stages + 1
        if frames <= 0:
            return np.zeros((stages, 0), dtype=np.int64)
        out = np.empty((stages, frames), dtype=np.int64)
        for k in range(stages):
            out[k] = grid[k][k:k + frames]
        return out
