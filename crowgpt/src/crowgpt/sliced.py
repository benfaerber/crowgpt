"""The training loss computed only over the ids each position may emit.

`CrowGPT.forward` builds logits over the whole vocabulary and then masks
all but the legal ids to minus infinity. A masked id contributes nothing to
the softmax, so the same loss comes from logits over the legal ids alone:
about 1,024 wide where the full row is over 8,000. Positions that share a
legal set (one per codebook, plus the prefix slots) are computed together.
"""
import torch
import torch.nn.functional as F


class LegalSlices:
    def __init__(self, legal):
        rows, self.class_of = torch.unique(legal.mask, dim=0, return_inverse=True)
        self.ids = [row.nonzero(as_tuple=True)[0] for row in rows]
        self.local = torch.full((len(rows), legal.mask.size(1)), -1, dtype=torch.long,
                                device=legal.mask.device)
        for n, ids in enumerate(self.ids):
            self.local[n, ids] = torch.arange(len(ids), device=ids.device)

    def loss(self, model, inputs, targets, shift=1, stage_weights=None):
        """Token-mean cross entropy, equal to `model(inputs, targets, legal)`.

        Optional `stage_weights` (sequence of K floats) scales each codec
        stage's contribution during training while leaving prefix and EOS at
        weight 1.0, normalised by the sum of token weights so loss scale stays
        comparable to unweighted cross entropy.
        """
        hidden = model.hidden(inputs)
        classes = self.class_of[shift : shift + inputs.size(1)]
        total = hidden.new_zeros((), dtype=torch.float32)
        weight_sum = hidden.new_zeros((), dtype=torch.float32)
        if stage_weights is not None:
            from crowgpt.codec import CODEBOOK_SIZE
            w_tensor = torch.as_tensor(stage_weights, device=inputs.device, dtype=torch.float32)
            codec_size = len(stage_weights) * CODEBOOK_SIZE
        else:
            w_tensor = None
            codec_size = 0

        for n in classes.unique().tolist():
            columns = (classes == n).nonzero(as_tuple=True)[0]
            wanted = targets[:, columns]
            real = wanted >= 0
            local = self.local[n][wanted.clamp(min=0)]
            if bool((local[real] < 0).any()):
                raise ValueError("a target is not legal at its position")
            logits = hidden[:, columns] @ model.head.weight[self.ids[n]].T
            if w_tensor is None:
                total = total + F.cross_entropy(
                    logits.reshape(-1, logits.size(-1)).float(),
                    torch.where(real, local, -1).reshape(-1),
                    ignore_index=-1, reduction="sum")
            else:
                per_tok = F.cross_entropy(
                    logits.reshape(-1, logits.size(-1)).float(),
                    torch.where(real, local, -1).reshape(-1),
                    ignore_index=-1, reduction="none")
                flat_wanted = wanted.reshape(-1)
                flat_real = real.reshape(-1)
                is_codec = flat_real & (flat_wanted < codec_size)
                tok_w = torch.where(flat_real, torch.ones_like(per_tok), torch.zeros_like(per_tok))
                if bool(is_codec.any()):
                    stages = (flat_wanted[is_codec] // CODEBOOK_SIZE).long()
                    tok_w[is_codec] = w_tensor[stages]
                total = total + (per_tok * tok_w).sum()
                weight_sum = weight_sum + tok_w.sum()
        if w_tensor is None:
            return total / (targets >= 0).sum()
        return total / weight_sum.clamp(min=1e-8)

    @torch.no_grad()
    def per_stage_sums(self, model, inputs, targets, vocabulary, shift=1):
        """Exact unweighted (loss_sum, token_count) broken down by stage, prefix, and EOS."""
        from crowgpt.codec import CODEBOOK_SIZE

        hidden = model.hidden(inputs)
        classes = self.class_of[shift : shift + inputs.size(1)]
        sums = {"prefix": 0.0, "eos": 0.0}
        counts = {"prefix": 0, "eos": 0}
        for s in range(vocabulary.n_codebooks):
            sums[f"stage_{s}"] = 0.0
            counts[f"stage_{s}"] = 0

        for n in classes.unique().tolist():
            columns = (classes == n).nonzero(as_tuple=True)[0]
            wanted = targets[:, columns]
            real = wanted >= 0
            if not bool(real.any()):
                continue
            local = self.local[n][wanted.clamp(min=0)]
            if bool((local[real] < 0).any()):
                raise ValueError("a target is not legal at its position")
            logits = hidden[:, columns] @ model.head.weight[self.ids[n]].T
            per_tok = F.cross_entropy(
                logits.reshape(-1, logits.size(-1)).float(),
                torch.where(real, local, -1).reshape(-1),
                ignore_index=-1, reduction="none")
            flat_wanted = wanted.reshape(-1)[real.reshape(-1)]
            flat_loss = per_tok[real.reshape(-1)]

            eos_mask = flat_wanted == vocabulary.eos
            if bool(eos_mask.any()):
                sums["eos"] += float(flat_loss[eos_mask].sum().item())
                counts["eos"] += int(eos_mask.sum().item())

            prefix_mask = flat_wanted > vocabulary.eos
            if bool(prefix_mask.any()):
                sums["prefix"] += float(flat_loss[prefix_mask].sum().item())
                counts["prefix"] += int(prefix_mask.sum().item())

            codec_mask = flat_wanted < vocabulary.codec_size
            if bool(codec_mask.any()):
                codec_stages = flat_wanted[codec_mask] // CODEBOOK_SIZE
                codec_losses = flat_loss[codec_mask]
                for s in range(vocabulary.n_codebooks):
                    sm = codec_stages == s
                    if bool(sm.any()):
                        sums[f"stage_{s}"] += float(codec_losses[sm].sum().item())
                        counts[f"stage_{s}"] += int(sm.sum().item())

        return sums, counts


def summarise_stage_sums(sums, counts, n_codebooks):
    """Turn accumulated per-category sums/counts into human-readable means."""
    total_loss = sum(sums.values())
    total_tokens = sum(counts.values())
    out = {
        "overall": total_loss / total_tokens if total_tokens else float("nan"),
        "total_tokens": int(total_tokens),
        "per_stage": {},
    }
    for key in ["prefix", *[f"stage_{s}" for s in range(n_codebooks)], "eos"]:
        c = counts.get(key, 0)
        out["per_stage"][key] = sums[key] / c if c else None
    coarse_loss = sum(sums.get(f"stage_{s}", 0.0) for s in range(min(3, n_codebooks)))
    coarse_n = sum(counts.get(f"stage_{s}", 0) for s in range(min(3, n_codebooks)))
    fine_loss = sum(sums.get(f"stage_{s}", 0.0) for s in range(max(0, n_codebooks - 3), n_codebooks))
    fine_n = sum(counts.get(f"stage_{s}", 0) for s in range(max(0, n_codebooks - 3), n_codebooks))
    out["coarse_0_2"] = coarse_loss / coarse_n if coarse_n else None
    out["fine_5_7"] = fine_loss / fine_n if fine_n else None
    return out
