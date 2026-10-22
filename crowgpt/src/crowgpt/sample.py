"""Generating bouts, and the control that proves the metrics can fail.

The duration bucket is sampled from the model rather than chosen, so lengths
come from what the corpus taught it about that species. Everything else is
ordinary nucleus-free top-k sampling, with the legality mask applied at every
step so a partial frame can never be emitted.

THE TEMPERATURE IS MEASURED, NOT TYPED, AND IT HAS MOVED TWICE. 0.95 was the
number that got written first. Experiment 0015 measured it on the undertrained
model and found 1.15 better: overlap with the training set fell from 8.7x the
held-out base rate to 1.0x at no cost in detection.

It is 1.0 now, and the reason 1.15 was chosen has gone away. On the model
trained properly on the bigger corpus, 1.0 gives ZERO overlap where 1.15 gives
0.8x, and beats it on everything else at once:

    T      duration   dynamic range   bursts   detected   overlap
    real     2.28 s        25.0 dB      3.79        83%        -
    0.85     2.22 s        27.8 dB      2.21        75%      9.0x
    1.00     2.20 s        24.4 dB      3.42        75%      0.0x
    1.15     1.75 s        23.5 dB      2.67        54%      0.8x

Ben found this by eye, not by metric: generated waveforms looked flat where real
ones rose and fell. The cause was duration — at 1.15 bouts come out 29% short,
so they hold fewer calls and show less contour. The burst RATE was right all
along, at about 1.6 per second either way.

The lesson worth keeping is that a sampling constant tuned against one
checkpoint does not transfer to a better one. 1.15 was correct for the model it
was measured on and cost 21 points of detection on this one.

`unigram` is the lower anchor for the judge: tokens drawn independently from
each codebook's marginal distribution, decoded the same way. It has the right
first-order statistics and no structure at all. If it scores well, the metric is
measuring something other than what we think.
"""

import json
from pathlib import Path

import numpy as np
import torch

from crowgpt.codec import CODEBOOK_SIZE, FRAME_RATE
from crowgpt.model import Config, CrowGPT, LegalMask
from crowgpt.tokens import TokenDataset, Vocabulary, codec_from_manifest


class Prefix:
    """The written conditioning tokens, and the count the model adds itself.

    `stated_len` is the ONE stripping offset — always equal to the
    vocabulary's `prefix_len`, whether the trailing slots (duration, unit
    bucket) end up sampled by the model or stated by the caller via
    `state()`. The two silent off-by-one bugs this replaces both came from
    a caller measuring the written list where it meant the stated length.
    """

    def __init__(self, written, sampled):
        self.written = list(written)
        self.sampled = sampled

    @property
    def stated_len(self):
        return len(self.written) + self.sampled

    def state(self, token):
        """Write a token the model would otherwise sample (duration first).

        `stated_len` is unchanged on purpose — the slot moves from the
        model's side of the ledger to the caller's, it does not stop
        existing.
        """
        if self.sampled <= 0:
            raise ValueError("no sampled slot left to state")
        self.written.append(token)
        self.sampled -= 1
        return self


class Sampler:
    def __init__(self, checkpoint, token_dir=None, device=None, decoder_state=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        # A dict is an already-assembled blob — crowgpt.hub builds one from
        # safetensors + JSON, where no pickled checkpoint ever exists.
        if isinstance(checkpoint, dict):
            blob = checkpoint
        else:
            blob = torch.load(checkpoint, map_location=self.device,
                              weights_only=False)
        self.manifest = blob["manifest"]
        self.config = Config(**blob["config"])
        self.model = CrowGPT(self.config).to(self.device).eval()
        self.model.load_state_dict(blob["model"])
        self.vocabulary = Vocabulary(self.manifest["n_codebooks"], self.manifest["species"],
                                     self.manifest.get("call_types", ()),
                                     self.manifest.get("channels", ()),
                                     n_unit_buckets=self.manifest.get("n_unit_buckets", 0))
        self.legal = LegalMask(self.vocabulary, self.config.block_size + 1, self.device)
        # Rebuilt from the manifest's own record of what wrote it, not from
        # bandwidth — see codec_from_manifest for the two ways that was wrong.
        self.codec = codec_from_manifest(self.manifest, device=self.device,
                                         decoder_state=decoder_state)
        self.token_dir = Path(token_dir) if token_dir else None

    @property
    def species(self):
        return self.manifest["species"]

    def _prefix(self, species, call_type=None, channel=None):
        """The conditioning a sequence starts from, as a `Prefix`.

        Returns an object rather than a list because the list's length was
        the seam that produced the same silent bug twice: `_prefix` writes
        fewer tokens than `prefix_len` claims (the model samples the rest),
        and a caller measuring the list where it meant the stated length
        shifted every codebook by one — audio that still decodes, numbers
        that mean nothing. `Prefix.written` is what goes into the tensor;
        `Prefix.stated_len` is the only stripping offset; the constructor
        asserts they agree with the vocabulary so no third count can exist.

        THE CHANNEL DEFAULTS TO ONE BUCKET, NOT TO A DRAW. The whole reason a
        channel-conditioned model exists is that an unconditioned one has to
        average over ~12,800 microphones, and 0042 measured what that averaging
        costs. Sampling the bucket per clip would hand that average straight
        back. So generation pins one nominal microphone unless told otherwise,
        and which one is a caller's choice worth making deliberately.
        """
        written = [self.vocabulary.species_token(species)]
        if self.vocabulary.call_types:
            written.append(self.vocabulary.calltype_token(call_type or "unknown"))
        if self.vocabulary.channels:
            written.append(self.vocabulary.channel_token(
                channel or self.vocabulary.channels[0]))
        prefix = Prefix(written, self.vocabulary.sampled_slots)
        assert prefix.stated_len == self.vocabulary.prefix_len
        return prefix

    @torch.no_grad()
    def tokens(self, species, temperature=1.0, top_k=200, seed=None, max_frames=225,
               call_type=None, channel=None):
        """One generated sequence of codec tokens, prefix and EOS stripped.

        `call_type` names what to ask for. Omitted, the model is handed
        "unknown" — the token most of its training carried — which is honest
        rather than silently picking a type on the caller's behalf.
        """
        if seed is not None:
            torch.manual_seed(seed)
        prefix = self._prefix(species, call_type, channel)
        sequence = torch.tensor([prefix.written],
                                device=self.device, dtype=torch.long)
        limit = min(self.config.block_size,
                    prefix.stated_len + max_frames * self.vocabulary.n_codebooks)

        # CACHED. The uncached path re-ran the whole prefix every step, so a
        # 1,800-token bout did about 1,800x the work of the token it was adding.
        # tests/test_kv_cache.py holds this to bit-equality with that path.
        cache = self.model.empty_cache()
        logits, _ = self.model(sequence, cache=cache, offset=0)
        # The legality mask walks the model through the sampled prefix slots
        # (duration, and the unit bucket when the vocabulary has one) before
        # any codec token, so the loop counts from the sequence actually
        # built while the strip below uses prefix.stated_len.
        for _ in range(limit - sequence.size(1)):
            grown = sequence.size(1)
            step = logits[:, -1, :].float()
            step = step.masked_fill(self.legal.forbidden[grown], float("-inf"))
            step = step / max(temperature, 1e-5)
            if top_k:
                kept = min(top_k, int((~torch.isinf(step)).sum().item()))
                if kept > 0:
                    cutoff = torch.topk(step, kept, dim=-1).values[:, [-1]]
                    step = step.masked_fill(step < cutoff, float("-inf"))
            nxt = torch.multinomial(torch.softmax(step, dim=-1), num_samples=1)
            if int(nxt) == self.vocabulary.eos:
                break
            sequence = torch.cat([sequence, nxt], dim=1)
            logits, _ = self.model(nxt, cache=cache, offset=grown)

        flat = sequence[0, prefix.stated_len:].cpu().numpy()
        usable = (flat.size // self.vocabulary.n_codebooks) * self.vocabulary.n_codebooks
        return flat[:usable].astype(np.int64)

    @torch.no_grad()
    def complete_fine(self, species, coarse_codes, from_stage=8, temperature=1.0,
                      top_k=200, seed=None, call_type=None, seconds=None, channel=None):
        """Fill stages >= from_stage, given the coarse ones, in the flat stream.

        The extender's inference path. Walk the interleaved sequence position by
        position; where the next slot belongs to a stage below the cut, FEED the
        given coarse code rather than sampling it, and where it is at or above,
        sample as usual. So every fine token is predicted from the complete
        same-frame coarse context, which is exactly what training scored.

        `coarse_codes` is [from_stage, frames], raw per-codebook entries as
        `Codec.encode` returns them — not flattened, and not offset into the
        vocabulary. Length comes from the coarse stream: it stops when the frames
        run out, and EOS is never sampled, because how long the bout is was
        already decided by whatever produced the coarse codes.

        Returns a flat token stream of the full n_codebooks, ready for
        `codec.unflatten`.
        """
        if seed is not None:
            torch.manual_seed(seed)
        if self.vocabulary.n_unit_buckets:
            # This path STATES the sampled tail (duration known from the
            # coarse stream) and would have to state a unit count it cannot
            # know. Refusing loudly beats a silent one-position shift — the
            # failure this method's own docstring warns about.
            raise NotImplementedError(
                "complete_fine does not support unit-bucket vocabularies")
        coarse = np.asarray(coarse_codes, dtype=np.int64)
        if coarse.shape[0] != from_stage:
            raise ValueError(
                f"coarse_codes has {coarse.shape[0]} stages, expected {from_stage}"
            )
        width = self.vocabulary.n_codebooks
        frames = int(coarse.shape[1])
        # THE DURATION TOKEN HAS TO BE WRITTEN, NOT SKIPPED. `tokens()` lets
        # the MODEL sample the duration bucket; here the length is already
        # known — the coarse stream fixed it — so the bucket is stated
        # through `Prefix.state`, which moves the slot to the written side
        # without changing `stated_len`. Leaving it out shifted the whole
        # stream by one position against the legality mask, silently: the
        # audio still decoded, every codebook was simply off by one.
        prefix = self._prefix(species, call_type, channel).state(
            self.vocabulary.duration_token(
                seconds if seconds is not None else frames / FRAME_RATE))
        sequence = torch.tensor([prefix.written], device=self.device,
                                dtype=torch.long)

        for position in range(frames * width):
            stage = position % width
            if stage < from_stage:
                # Offset into this stage's slice of the vocabulary, the same way
                # Codec.flatten does. Feeding a bare entry would land in
                # codebook 0 and be silently wrong for every stage but the first.
                token = int(coarse[stage, position // width]) + stage * CODEBOOK_SIZE
                nxt = torch.tensor([[token]], device=self.device, dtype=torch.long)
            else:
                window = sequence[:, -self.config.block_size:]
                logits, _ = self.model(window)
                step = logits[:, -1, :].float()
                step = step.masked_fill(self.legal.forbidden[window.size(1)], float("-inf"))
                # EOS is legal at frame boundaries and must not be taken: the
                # length is the coarse stream's to decide, and an early stop here
                # would truncate audio whose structure was already fixed.
                step[:, self.vocabulary.eos] = float("-inf")
                step = step / max(temperature, 1e-5)
                if top_k:
                    kept = min(top_k, int((~torch.isinf(step)).sum().item()))
                    if kept > 0:
                        cutoff = torch.topk(step, kept, dim=-1).values[:, [-1]]
                        step = step.masked_fill(step < cutoff, float("-inf"))
                nxt = torch.multinomial(torch.softmax(step, dim=-1), num_samples=1)
            sequence = torch.cat([sequence, nxt], dim=1)

        return sequence[0, prefix.stated_len:].cpu().numpy().astype(np.int64)

    @torch.no_grad()
    def continue_from(self, species, prompt_codes, temperature=1.0, top_k=200, seed=None,
                      max_frames=225, call_type=None, seconds=None, channel=None):
        """Free-run from a real bout's opening frames, and return only what follows.

        The species token says which bird. It does not say which microphone, and
        0042 measures that the microphone moves timbre 6.2x further than anything
        inside one microphone does. So an unprompted sample has to average over
        every channel in the corpus, and this is the way to ask what the model
        would do if it did not have to: hand it real codec tokens from one
        recording and let it continue them. The channel is pinned by example, at
        no training cost, because a causal model conditions on whatever is in its
        context whether or not there is a token for it.

        `prompt_codes` is [K, frames] as `Codec.encode` returns it — raw entries,
        not flattened and not offset. `seconds` states the length of the bout the
        prompt was cut from; left None the duration bucket is sampled, exactly as
        `tokens()` does. Passing the source bout's true duration is the fair
        comparison and is what experiment 0043 uses.

        Returns the continuation alone, prompt and prefix stripped, so a
        measurement cannot be flattered by the real tokens that seeded it.
        """
        if seed is not None:
            torch.manual_seed(seed)
        if self.vocabulary.n_unit_buckets:
            raise NotImplementedError(
                "continue_from does not support unit-bucket vocabularies")
        prompt = np.asarray(prompt_codes, dtype=np.int64)
        width = self.vocabulary.n_codebooks
        if prompt.ndim != 2 or prompt.shape[0] != width:
            raise ValueError(f"prompt_codes must be [{width}, frames], got {prompt.shape}")
        if prompt.shape[1] < 1:
            raise ValueError("the prompt needs at least one frame")

        prefix = self._prefix(species, call_type, channel)
        sequence = torch.tensor([prefix.written],
                                device=self.device, dtype=torch.long)
        cache = self.model.empty_cache()
        logits, _ = self.model(sequence, cache=cache, offset=0)

        if seconds is None:
            duration = int(self._draw(logits, sequence.size(1), temperature, top_k))
        else:
            duration = self.vocabulary.duration_token(seconds)

        seeded = self.codec.flatten(prompt).astype(np.int64).tolist()
        head = torch.tensor([[duration] + seeded], device=self.device, dtype=torch.long)
        offset = sequence.size(1)
        sequence = torch.cat([sequence, head], dim=1)
        logits, _ = self.model(head, cache=cache, offset=offset)

        limit = min(self.config.block_size,
                    prefix.stated_len + max_frames * width)
        for _ in range(limit - sequence.size(1)):
            grown = sequence.size(1)
            nxt = self._draw(logits, grown, temperature, top_k)
            if int(nxt) == self.vocabulary.eos:
                break
            nxt = nxt.view(1, 1)
            sequence = torch.cat([sequence, nxt], dim=1)
            logits, _ = self.model(nxt, cache=cache, offset=grown)

        flat = sequence[0, prefix.stated_len + len(seeded):].cpu().numpy()
        usable = (flat.size // width) * width
        return flat[:usable].astype(np.int64)

    def _draw(self, logits, position, temperature, top_k):
        """One masked, tempered, top-k draw from the last position's logits.

        Shared so `continue_from` cannot drift from `tokens()` in the mask, the
        temperature or the truncation — the three places a sampler goes wrong
        silently rather than loudly.
        """
        step = logits[:, -1, :].float()
        step = step.masked_fill(self.legal.forbidden[position], float("-inf"))
        step = step / max(temperature, 1e-5)
        if top_k:
            kept = min(top_k, int((~torch.isinf(step)).sum().item()))
            if kept > 0:
                cutoff = torch.topk(step, kept, dim=-1).values[:, [-1]]
                step = step.masked_fill(step < cutoff, float("-inf"))
        return torch.multinomial(torch.softmax(step, dim=-1), num_samples=1)

    @torch.no_grad()
    def batch_tokens(self, species_list, temperature=1.0, top_k=200, seed=None,
                     max_frames=225, call_type=None, channel=None):
        """Generate many bouts at once.

        MEASURED SLOWER THAN GENERATING ONE AT A TIME, and kept anyway because
        the reason is worth writing down. There is no KV cache: every step
        re-runs the forward pass over the whole sequence so far, making the cost
        of a bout quadratic in its length. Batched, every sequence runs to the
        LONGEST one's length, so a batch of 24 does 24 x T_max^2 work against
        the sum of T_i^2 one at a time — about twice as much here. Batching only
        pays when steps are latency-bound, and these are compute-bound.

        A KV cache now exists and `tokens()` uses it. MEASURED AT 1.7x, NOT THE
        THOUSANDFOLD THIS USED TO CLAIM — that number was about FLOPs, and FLOPs
        were never the constraint. At 1,800 tokens with a 22M model the GPU is
        nowhere near saturated: the cost is ~1,800 Python iterations and kernel
        launches per bout, which a cache does not remove. Generation here is
        latency-bound, so eliminating redundant arithmetic buys less than it
        looks like it should.
        Until then, prefer `audio()` in a loop.

        Every sequence in the batch sits at the same position, so they share one
        legality mask — the thing that makes this simple rather than fiddly.

        Sequences finish at different lengths. A finished one keeps being fed
        through the model and its output is discarded, which wastes a little
        compute and is far simpler than compacting the batch mid-generation.

        `call_type` is one name for the whole batch, or a list parallel to
        `species_list`. It must be written into the prefix rather than left to
        the model: the legality mask would happily sample a call type at that
        position, and the tail below strips a fixed prefix, so a short prefix
        leaves the duration token sitting in the codec stream and shifts every
        codebook by one.
        """
        if seed is not None:
            torch.manual_seed(seed)
        n = len(species_list)
        wanted = call_type if isinstance(call_type, (list, tuple)) else [call_type] * n
        prefixes = [self._prefix(s, c, channel)
                    for s, c in zip(species_list, wanted)]
        stated_len = prefixes[0].stated_len
        sequence = torch.tensor([p.written for p in prefixes],
                                device=self.device, dtype=torch.long)
        limit = min(self.config.block_size,
                    stated_len + max_frames * self.vocabulary.n_codebooks)
        done = torch.zeros(n, dtype=torch.bool, device=self.device)
        length = torch.full((n,), limit, dtype=torch.long, device=self.device)

        # From the built sequence, not prefix_len — same seam note as tokens().
        for _ in range(limit - sequence.size(1)):
            position = sequence.size(1)
            logits, _ = self.model(sequence[:, -self.config.block_size :])
            step = logits[:, -1, :].float()
            step = step.masked_fill(self.legal.forbidden[position], float("-inf"))
            step = step / max(temperature, 1e-5)
            if top_k:
                # How many ids are legal here is a property of the mask, not of
                # the logits, so it can be counted without asking the GPU. The
                # .item() this replaces forced a device sync on every one of
                # ~1,800 steps and made batching slower than not batching.
                kept = min(top_k, int(self.legal.legal_count(position)))
                if kept > 0:
                    cutoff = torch.topk(step, kept, dim=-1).values[:, [-1]]
                    step = step.masked_fill(step < cutoff, float("-inf"))
            nxt = torch.multinomial(torch.softmax(step, dim=-1), num_samples=1).squeeze(1)

            finishing = (nxt == self.vocabulary.eos) & ~done
            length = torch.where(finishing, torch.full_like(length, position), length)
            done = done | finishing
            # A finished sequence is padded with its own last token; the tail is
            # cut off below, so what it is does not matter, only that it decodes.
            nxt = torch.where(done, sequence[:, -1], nxt)
            sequence = torch.cat([sequence, nxt.unsqueeze(1)], dim=1)
            # Checking every step is a second sync per step; every 32 costs at
            # most 32 wasted steps at the very end.
            if position % 32 == 0 and bool(done.all()):
                break

        out = []
        k = self.vocabulary.n_codebooks
        for i in range(n):
            flat = sequence[i, stated_len : int(length[i])].cpu().numpy()
            usable = (flat.size // k) * k
            out.append(flat[:usable].astype(np.int64))
        return out

    def audio(self, species, **kwargs):
        flat = self.tokens(species, **kwargs)
        if flat.size == 0:
            return np.zeros(0, dtype=np.float32)
        codes = self.codec.unflatten(flat)
        return self.codec.decode(torch.from_numpy(codes))[0]

    def unigram(self, n_frames, seed=0):
        """Decoded noise with the right marginals — the lower anchor."""
        rng = np.random.default_rng(seed)
        marginals = self._marginals()
        codes = np.stack(
            [rng.choice(len(p), size=n_frames, p=p) for p in marginals]
        ).astype(np.int64)
        return self.codec.decode(torch.from_numpy(codes))[0]

    def _marginals(self):
        if getattr(self, "_cached_marginals", None) is not None:
            return self._cached_marginals
        if self.token_dir is None:
            raise SystemExit("unigram control needs token_dir")
        dataset = TokenDataset(self.token_dir, "train")
        n_codebooks = self.vocabulary.n_codebooks
        counts = np.ones((n_codebooks, 1024))
        for i in range(min(len(dataset), 4000)):
            sequence = dataset.sequence(i)[self.vocabulary.prefix_len : -1]
            usable = (sequence.size // n_codebooks) * n_codebooks
            if usable == 0:
                continue
            grid = self.codec.unflatten(sequence[:usable])
            for stage in range(n_codebooks):
                counts[stage] += np.bincount(grid[stage], minlength=1024)
        self._cached_marginals = counts / counts.sum(axis=1, keepdims=True)
        return self._cached_marginals


def write_samples(sampler, out_dir, per_species=8, sample_rate=24000, **kwargs):
    import soundfile as sf

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for s, slug in enumerate(sampler.species):
        for i in range(per_species):
            samples = sampler.audio(slug, seed=s * 1000 + i, **kwargs)
            if samples.size == 0:
                continue
            path = out_dir / f"{slug}-{i:02d}.wav"
            sf.write(str(path), samples, sample_rate, subtype="PCM_16")
            written.append({"path": str(path), "species": slug, "dur_sec": round(samples.size / sample_rate, 3)})
    (out_dir / "samples.json").write_text(json.dumps(written, indent=2))
    return written
