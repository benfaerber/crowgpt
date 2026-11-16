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

    def loss(self, model, inputs, targets, shift=1):
        """Token-mean cross entropy, equal to `model(inputs, targets, legal)`."""
        hidden = model.hidden(inputs)
        classes = self.class_of[shift : shift + inputs.size(1)]
        total = hidden.new_zeros((), dtype=torch.float32)
        for n in classes.unique().tolist():
            columns = (classes == n).nonzero(as_tuple=True)[0]
            wanted = targets[:, columns]
            real = wanted >= 0
            local = self.local[n][wanted.clamp(min=0)]
            if bool((local[real] < 0).any()):
                raise ValueError("a target is not legal at its position")
            logits = hidden[:, columns] @ model.head.weight[self.ids[n]].T
            total = total + F.cross_entropy(
                logits.reshape(-1, logits.size(-1)).float(),
                torch.where(real, local, -1).reshape(-1),
                ignore_index=-1, reduction="sum")
        return total / (targets >= 0).sum()
