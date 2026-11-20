"""Dual-AR (Temporal + Depth) CrowGPT over EnCodec tokens.

Flat interleaving feeds one transformer a 3,600-token stream for 6 seconds of
8-codebook audio, spending quadratic attention and 7/8 of its sequence slots on
intra-frame residual codebooks. Dual-AR factors the exact same joint probability
P(x_1..x_N | x_0) into two matched pieces:

  - Temporal backbone (frame rate, 75 Hz): sees prefix tokens plus one vector
    per frame (the normalised sum of that frame's K codebook embeddings), so 6 s
    is ~453 positions instead of 3,603 (~64x less attention FLOPs).
  - Depth transformer (length K=8): takes each frame's temporal hidden state
    h_t and autoregressively predicts codebooks c_{t,0} -> ... -> c_{t,K-1}
    (with EOS allowed only at stage 0, matching flat CrowGPT's legal mask).

Because the joint distribution and per-position legal sets are identical to
flat CrowGPT, total NLL/token and per-stage NLL (prefix, stage_0..7, eos) are
directly apples-to-apples comparable on the same token memmaps.
"""

import math

import numpy as np
import torch
import torch.nn as nn
from torch.nn import functional as F

from crowgpt.codec import CODEBOOK_SIZE
from crowgpt.model import Block, make_norm, rope_cos_sin


class DualARConfig:
    def __init__(
        self,
        vocab_size,
        n_codebooks,
        block_size=4096,
        n_layer=6,
        depth_layer=2,
        n_head=4,
        depth_head=4,
        n_embd=384,
        dropout=0.0,
        prefix_len=3,
        norm="rmsnorm",
        mlp="swiglu",
        rope_base=10000.0,
    ):
        self.vocab_size = vocab_size
        self.n_codebooks = n_codebooks
        self.block_size = block_size
        self.n_layer = n_layer
        self.depth_layer = depth_layer
        self.n_head = n_head
        self.depth_head = depth_head
        self.n_embd = n_embd
        self.dropout = dropout
        self.prefix_len = prefix_len
        self.norm = norm
        self.mlp = mlp
        self.rope_base = rope_base
        self.arch = "dualar"

    def as_dict(self):
        return dict(self.__dict__)


class _BlockConfig:
    """Adapter exposing the fields `Block` reads."""

    def __init__(self, n_embd, n_head, dropout, norm, mlp, rope_base):
        self.n_embd = n_embd
        self.n_head = n_head
        self.dropout = dropout
        self.norm = norm
        self.mlp = mlp
        self.rope_base = rope_base


class DualARCrowGPT(nn.Module):
    def __init__(self, config: DualARConfig):
        super().__init__()
        self.config = config
        self.n_codebooks = config.n_codebooks
        self.prefix_len = config.prefix_len
        self.eos = CODEBOOK_SIZE * config.n_codebooks

        self.token_embedding = nn.Embedding(config.vocab_size, config.n_embd)
        self.frame_norm = make_norm(config.norm, config.n_embd)
        self.drop = nn.Dropout(config.dropout)

        t_cfg = _BlockConfig(
            config.n_embd, config.n_head, config.dropout,
            config.norm, config.mlp, config.rope_base,
        )
        d_cfg = _BlockConfig(
            config.n_embd, config.depth_head, config.dropout,
            config.norm, config.mlp, config.rope_base,
        )
        self.temporal_blocks = nn.ModuleList([Block(t_cfg) for _ in range(config.n_layer)])
        self.temporal_ln_f = make_norm(config.norm, config.n_embd)

        self.depth_pos = nn.Embedding(config.n_codebooks, config.n_embd)
        self.depth_blocks = nn.ModuleList([Block(d_cfg) for _ in range(config.depth_layer)])
        self.depth_ln_f = make_norm(config.norm, config.n_embd)

        self.head = nn.Linear(config.n_embd, config.vocab_size, bias=False)
        self.head.weight = self.token_embedding.weight

        # Precompute legal token id lists for stage 0 (+EOS) and stages 1..K-1.
        stage0_ids = torch.cat([
            torch.arange(0, CODEBOOK_SIZE, dtype=torch.long),
            torch.tensor([self.eos], dtype=torch.long),
        ])
        self.register_buffer("stage0_ids", stage0_ids, persistent=False)

        self.apply(self._init_weights)
        for name, parameter in self.named_parameters():
            if (
                name.endswith("proj.weight")
                or name.endswith("mlp.2.weight")
                or name.endswith("mlp.down.weight")
            ):
                depth = config.n_layer if name.startswith("temporal_blocks") else config.depth_layer
                nn.init.normal_(parameter, mean=0.0, std=0.02 / math.sqrt(2 * max(1, depth)))

    @staticmethod
    def _init_weights(module):
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def n_params(self):
        return sum(p.numel() for p in self.parameters())

    def empty_temporal_cache(self):
        return [[] for _ in self.temporal_blocks]

    def empty_depth_cache(self):
        return [[] for _ in self.depth_blocks]

    def embed_frames(self, frame_tokens):
        """[B, F, K] codec token ids -> [B, F, D] summed & normalised frame vectors."""
        emb = self.token_embedding(frame_tokens).sum(dim=2) / math.sqrt(self.n_codebooks)
        return self.frame_norm(emb)

    def temporal_hidden(self, x, cache=None, offset=0):
        """Run the frame-rate causal backbone with RoPE."""
        positions = torch.arange(offset, offset + x.size(1), device=x.device)
        cos_sin = rope_cos_sin(
            positions,
            self.config.n_embd // self.config.n_head,
            x.device,
            x.dtype,
            base=self.config.rope_base,
        )
        x = self.drop(x)
        for n, block in enumerate(self.temporal_blocks):
            x = block(x, cache=None if cache is None else cache[n], rope_pos=cos_sin)
        return self.temporal_ln_f(x)

    def depth_hidden(self, x, cache=None, offset=0):
        """Run the intra-frame causal depth transformer (length <= K)."""
        positions = torch.arange(offset, offset + x.size(1), device=x.device)
        x = self.drop(x + self.depth_pos(positions)[None, :, :])
        for n, block in enumerate(self.depth_blocks):
            x = block(x, cache=None if cache is None else cache[n], rope_pos=None)
        return self.depth_ln_f(x)

    def _unpack_batch(self, inputs, targets):
        """Split flat [B, L] inputs/targets into prefix + frame-aligned tensors."""
        batch, length = inputs.shape
        p = self.prefix_len
        k = self.n_codebooks
        rem = max(0, length - p)
        f_in = (rem + k - 1) // k

        in_need = p + f_in * k
        if length < in_need:
            pad_in = inputs.new_zeros((batch, in_need - length))
            inputs_pad = torch.cat([inputs, pad_in], dim=1)
        else:
            inputs_pad = inputs

        f_pred = f_in + 1
        tgt_need = (p - 1) + f_pred * k
        if targets.size(1) < tgt_need:
            pad_t = targets.new_full((batch, tgt_need - targets.size(1)), -1)
            targets_pad = torch.cat([targets, pad_t], dim=1)
        else:
            targets_pad = targets[:, :tgt_need]

        prefix_in = inputs_pad[:, :p]
        frame_in = inputs_pad[:, p:in_need].view(batch, f_in, k) if f_in else None
        prefix_tgt = targets_pad[:, : p - 1]
        frame_tgt = targets_pad[:, p - 1 : tgt_need].view(batch, f_pred, k)
        return prefix_in, frame_in, prefix_tgt, frame_tgt

    def _forward_per_token(self, inputs, targets, vocabulary):
        """Compute exact per-token losses for prefix slots and every frame stage."""
        prefix_in, frame_in, prefix_tgt, frame_tgt = self._unpack_batch(inputs, targets)
        p = self.prefix_len
        k = self.n_codebooks

        t_emb = self.token_embedding(prefix_in)
        if frame_in is not None and frame_in.size(1) > 0:
            f_emb = self.embed_frames(frame_in)
            t_in = torch.cat([t_emb, f_emb], dim=1)
        else:
            t_in = t_emb

        h = self.temporal_hidden(t_in)  # [B, P + F_in, D]
        slots = vocabulary.prefix_slots()

        # Prefix targets: positions 0 .. P-2 predict slots 1 .. P-1.
        prefix_losses = []
        prefix_valid = []
        for pos in range(p - 1):
            start, end = slots[pos + 1]
            wanted = prefix_tgt[:, pos]
            real = wanted >= 0
            if not bool(real.any()):
                continue
            local = wanted - start
            if bool(((local[real] < 0) | (local[real] >= end - start)).any()):
                raise ValueError(f"illegal prefix target at slot {pos + 1}")
            logits = h[:, pos] @ self.head.weight[start:end].T
            loss_vec = F.cross_entropy(
                logits.float(),
                torch.where(real, local, -1),
                ignore_index=-1,
                reduction="none",
            )
            prefix_losses.append(loss_vec[real])
            prefix_valid.append(wanted[real])

        # Frame targets: temporal states h[:, P-1:] drive frames 0 .. F_in.
        h_frames = h[:, p - 1 :]  # [B, F_pred, D]
        active = (frame_tgt >= 0).any(dim=-1)  # [B, F_pred]
        stage_losses = {}
        stage_targets = {}
        if bool(active.any()):
            h_act = h_frames[active]          # [N, D]
            ft_act = frame_tgt[active]        # [N, K]
            prev_toks = ft_act[:, : k - 1].clamp(min=0)
            prev_emb = self.token_embedding(prev_toks)  # [N, K-1, D]
            depth_in = torch.cat([h_act.unsqueeze(1), prev_emb], dim=1)  # [N, K, D]
            dh = self.depth_hidden(depth_in)  # [N, K, D]

            # Stage 0 + EOS (1025-way).
            w0 = ft_act[:, 0]
            r0 = w0 >= 0
            if bool(r0.any()):
                is_eos = w0 == self.eos
                local0 = torch.where(is_eos, torch.full_like(w0, CODEBOOK_SIZE), w0)
                if bool(((local0[r0] < 0) | (local0[r0] > CODEBOOK_SIZE)).any()):
                    raise ValueError("illegal stage-0/EOS target")
                logits0 = dh[:, 0] @ self.head.weight[self.stage0_ids].T
                l0 = F.cross_entropy(
                    logits0.float(),
                    torch.where(r0, local0, -1),
                    ignore_index=-1,
                    reduction="none",
                )
                stage_losses[0] = l0[r0]
                stage_targets[0] = w0[r0]

            # Stages 1 .. K-1 (1024-way each).
            for s in range(1, k):
                ws = ft_act[:, s]
                rs = ws >= 0
                if not bool(rs.any()):
                    continue
                lo = s * CODEBOOK_SIZE
                hi = (s + 1) * CODEBOOK_SIZE
                local_s = ws - lo
                if bool(((local_s[rs] < 0) | (local_s[rs] >= CODEBOOK_SIZE)).any()):
                    raise ValueError(f"illegal stage-{s} target")
                logits_s = dh[:, s] @ self.head.weight[lo:hi].T
                ls = F.cross_entropy(
                    logits_s.float(),
                    torch.where(rs, local_s, -1),
                    ignore_index=-1,
                    reduction="none",
                )
                stage_losses[s] = ls[rs]
                stage_targets[s] = ws[rs]

        return prefix_losses, stage_losses, stage_targets

    def loss(self, inputs, targets, vocabulary, stage_weights=None):
        """Token-mean cross entropy (optionally weighted per codec stage)."""
        prefix_losses, stage_losses, stage_targets = self._forward_per_token(
            inputs, targets, vocabulary
        )
        total = self.token_embedding.weight.new_zeros((), dtype=torch.float32)
        w_sum = self.token_embedding.weight.new_zeros((), dtype=torch.float32)

        for vec in prefix_losses:
            total = total + vec.sum()
            w_sum = w_sum + vec.numel()

        for s, vec in stage_losses.items():
            if stage_weights is None:
                total = total + vec.sum()
                w_sum = w_sum + vec.numel()
            else:
                ws = float(stage_weights[s])
                if s == 0:
                    is_eos = stage_targets[0] == self.eos
                    weights = torch.where(
                        is_eos,
                        torch.ones_like(vec),
                        torch.full_like(vec, ws),
                    )
                    total = total + (vec * weights).sum()
                    w_sum = w_sum + weights.sum()
                else:
                    total = total + vec.sum() * ws
                    w_sum = w_sum + vec.numel() * ws

        return total / w_sum.clamp(min=1e-8)

    @torch.no_grad()
    def per_stage_sums(self, inputs, targets, vocabulary):
        """Exact unweighted (loss_sum, token_count) per category, matching LegalSlices."""
        prefix_losses, stage_losses, stage_targets = self._forward_per_token(
            inputs, targets, vocabulary
        )
        sums = {"prefix": 0.0, "eos": 0.0}
        counts = {"prefix": 0, "eos": 0}
        for s in range(self.n_codebooks):
            sums[f"stage_{s}"] = 0.0
            counts[f"stage_{s}"] = 0

        for vec in prefix_losses:
            sums["prefix"] += float(vec.sum().item())
            counts["prefix"] += int(vec.numel())

        for s, vec in stage_losses.items():
            if s == 0:
                is_eos = stage_targets[0] == self.eos
                if bool(is_eos.any()):
                    sums["eos"] += float(vec[is_eos].sum().item())
                    counts["eos"] += int(is_eos.sum().item())
                non_eos = ~is_eos
                if bool(non_eos.any()):
                    sums["stage_0"] += float(vec[non_eos].sum().item())
                    counts["stage_0"] += int(non_eos.sum().item())
            else:
                sums[f"stage_{s}"] += float(vec.sum().item())
                counts[f"stage_{s}"] += int(vec.numel())

        return sums, counts

    def optimiser(self, learning_rate, weight_decay=0.1, betas=(0.9, 0.95), fused=False):
        """Decay matmul and embedding weights, never gains and biases."""
        decay, no_decay = [], []
        for parameter in self.parameters():
            if not parameter.requires_grad:
                continue
            (decay if parameter.dim() >= 2 else no_decay).append(parameter)
        kwargs = dict(lr=learning_rate, betas=betas)
        if fused:
            kwargs["fused"] = True
        return torch.optim.AdamW(
            [
                {"params": decay, "weight_decay": weight_decay},
                {"params": no_decay, "weight_decay": 0.0},
            ],
            **kwargs,
        )


class DualARSampler:
    """Sampler for DualARCrowGPT, matching `crowgpt.sample.Sampler`'s interface."""

    def __init__(self, checkpoint, device=None, decoder_state=None):
        from crowgpt.tokens import Vocabulary, codec_from_manifest

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if isinstance(checkpoint, dict):
            blob = checkpoint
        else:
            blob = torch.load(checkpoint, map_location=self.device, weights_only=False)
        self.manifest = blob["manifest"]
        cfg_dict = {k: v for k, v in blob["config"].items() if k != "arch"}
        self.config = DualARConfig(**cfg_dict)
        self.model = DualARCrowGPT(self.config).to(self.device).eval()
        self.model.load_state_dict(blob["model"])
        self.vocabulary = Vocabulary(
            self.manifest["n_codebooks"],
            self.manifest["species"],
            self.manifest.get("call_types", ()),
            self.manifest.get("channels", ()),
            n_unit_buckets=self.manifest.get("n_unit_buckets", 0),
        )
        self.codec = codec_from_manifest(
            self.manifest, device=self.device, decoder_state=decoder_state
        )

    @property
    def species(self):
        return self.manifest["species"]

    def _prefix_written(self, species, call_type=None, channel=None):
        written = [self.vocabulary.species_token(species)]
        if self.vocabulary.call_types:
            written.append(self.vocabulary.calltype_token(call_type or "unknown"))
        if self.vocabulary.channels:
            if channel is None:
                raise ValueError("channel must be specified explicitly for channel-conditioned models")
            written.append(self.vocabulary.channel_token(channel))
        return written

    @torch.no_grad()
    def tokens(
        self,
        species,
        temperature=1.0,
        top_k=200,
        seed=None,
        max_frames=225,
        call_type=None,
        channel=None,
        min_p=None,
        stage_temperatures=None,
        repeat_penalty=1.0,
    ):
        from crowgpt.sample import draw_from_logits

        if seed is not None:
            torch.manual_seed(seed)
        k = self.vocabulary.n_codebooks
        written = self._prefix_written(species, call_type, channel)
        slots = self.vocabulary.prefix_slots()

        t_cache = self.model.empty_temporal_cache()
        prefix_tensor = torch.tensor([written], device=self.device, dtype=torch.long)
        h = self.model.temporal_hidden(
            self.model.token_embedding(prefix_tensor), cache=t_cache, offset=0
        )
        t_pos = len(written)

        # Sample trailing prefix slots (unit bucket, duration).
        while t_pos < self.vocabulary.prefix_len:
            start, end = slots[t_pos]
            logits = h[:, -1, :] @ self.model.head.weight[start:end].T
            local = draw_from_logits(logits, temperature=temperature, top_k=top_k, min_p=min_p)
            tok = int(local.item()) + start
            tok_tensor = torch.tensor([[tok]], device=self.device, dtype=torch.long)
            h = self.model.temporal_hidden(
                self.model.token_embedding(tok_tensor), cache=t_cache, offset=t_pos
            )
            t_pos += 1

        # Autoregressive frame loop: Depth Transformer (length K) + 1 Temporal step.
        frames = []
        prev_frame = None
        for _ in range(max_frames):
            d_cache = self.model.empty_depth_cache()
            h_t = h[:, -1:, :]  # [1, 1, D]
            dh = self.model.depth_hidden(h_t, cache=d_cache, offset=0)

            t0 = stage_temperatures[0] if stage_temperatures is not None else temperature
            logits0 = dh[:, -1, :] @ self.model.head.weight[self.model.stage0_ids].T
            rep0 = prev_frame[0] if (prev_frame is not None and repeat_penalty != 1.0) else None
            idx0 = int(
                draw_from_logits(
                    logits0,
                    temperature=t0,
                    top_k=top_k,
                    min_p=min_p,
                    repeat_token=rep0,
                    repeat_penalty=repeat_penalty,
                ).item()
            )
            if idx0 == CODEBOOK_SIZE:
                break

            frame = [idx0]
            prev_tok_id = idx0
            for s in range(1, k):
                tok_emb = self.model.token_embedding(
                    torch.tensor([[prev_tok_id]], device=self.device, dtype=torch.long)
                )
                dh = self.model.depth_hidden(tok_emb, cache=d_cache, offset=s)
                lo = s * CODEBOOK_SIZE
                hi = (s + 1) * CODEBOOK_SIZE
                ts = stage_temperatures[s] if stage_temperatures is not None else temperature
                logits_s = dh[:, -1, :] @ self.model.head.weight[lo:hi].T
                reps = (
                    prev_frame[s] - lo
                    if (prev_frame is not None and repeat_penalty != 1.0)
                    else None
                )
                local_s = int(
                    draw_from_logits(
                        logits_s,
                        temperature=ts,
                        top_k=top_k,
                        min_p=min_p,
                        repeat_token=reps,
                        repeat_penalty=repeat_penalty,
                    ).item()
                )
                prev_tok_id = lo + local_s
                frame.append(prev_tok_id)

            frames.append(frame)
            prev_frame = frame
            frame_tensor = torch.tensor([[frame]], device=self.device, dtype=torch.long)
            f_emb = self.model.embed_frames(frame_tensor)
            h = self.model.temporal_hidden(f_emb, cache=t_cache, offset=t_pos)
            t_pos += 1

        if not frames:
            return np.zeros(0, dtype=np.int64)
        return np.asarray(frames, dtype=np.int64).reshape(-1)

    def audio(self, species, **kwargs):
        flat = self.tokens(species, **kwargs)
        if flat.size == 0:
            return np.zeros(0, dtype=np.float32)
        codes = self.codec.unflatten(flat)
        return self.codec.decode(torch.from_numpy(codes))[0]
