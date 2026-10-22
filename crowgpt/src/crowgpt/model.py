"""The GPT part of CrowGPT.

A small causal transformer over flattened EnCodec tokens. Small deliberately:
the corpus is a few million tokens but only a couple of thousand independent
recordings, and a 25M-parameter model on that memorises rather than learns. At
d=256 x 6 layers this is about 6M parameters, which is roughly the size the data
can actually support, and it trains in minutes on one GPU.

The one structural thing this model knows that a text GPT does not: position
determines which codebook comes next. At offset j into the codec stream the next
token must belong to codebook j % K, so every other codebook's ids are masked to
-inf. That is not an optimisation — an unmasked model spends most of its output
layer on tokens that cannot occur, and can emit an id mid-frame that will not
decode. EOS is masked everywhere except frame boundaries for the same reason.
"""

import math

import torch
import torch.nn as nn
from torch.nn import functional as F


class Config:
    def __init__(
        self,
        vocab_size,
        n_codebooks,
        block_size=1024,
        n_layer=6,
        n_head=4,
        n_embd=256,
        dropout=0.25,
        prefix_len=2,
    ):
        self.vocab_size = vocab_size
        self.n_codebooks = n_codebooks
        self.block_size = block_size
        self.n_layer = n_layer
        self.n_head = n_head
        self.n_embd = n_embd
        self.dropout = dropout
        self.prefix_len = prefix_len

    def as_dict(self):
        return dict(self.__dict__)


class SelfAttention(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.n_head = config.n_head
        self.n_embd = config.n_embd
        self.qkv = nn.Linear(config.n_embd, 3 * config.n_embd, bias=False)
        self.proj = nn.Linear(config.n_embd, config.n_embd, bias=False)
        self.dropout = config.dropout
        self.resid_drop = nn.Dropout(config.dropout)

    def forward(self, x, cache=None):
        """`cache` is a [k, v] pair of past keys and values, extended in place.

        WITHOUT IT, GENERATION RECOMPUTES THE WHOLE PREFIX EVERY STEP. A bout is
        ~1,800 tokens at eight codebooks, so a full pass per token does about
        1,800x the work of the one token that is new — quadratic in bout length,
        and the reason sampling has always been the slow half of every
        experiment here.

        IS_CAUSAL MUST GO OFF WHEN THE CACHE IS ON, and this is the subtle part.
        With a cache the query is a single new token and the keys are the whole
        history, so the mask is not square; `is_causal=True` on a 1xT attention
        masks almost everything and the model silently attends to nothing but
        the first key. A single new token after a full history needs NO mask at
        all — everything it can see is already in the past.
        """
        batch, time, channels = x.shape
        q, k, v = self.qkv(x).split(self.n_embd, dim=2)
        shape = (batch, time, self.n_head, channels // self.n_head)
        q, k, v = (t.view(*shape).transpose(1, 2) for t in (q, k, v))

        if cache is not None:
            if cache:
                k = torch.cat([cache[0], k], dim=2)
                v = torch.cat([cache[1], v], dim=2)
            cache[:] = [k, v]
            # Square only on the priming pass, when q and k are the same length.
            causal = q.size(2) == k.size(2) and q.size(2) > 1
        else:
            causal = True

        out = F.scaled_dot_product_attention(
            q, k, v, dropout_p=self.dropout if self.training else 0.0, is_causal=causal
        )
        out = out.transpose(1, 2).contiguous().view(batch, time, channels)
        return self.resid_drop(self.proj(out))


class Block(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.n_embd)
        self.attn = SelfAttention(config)
        self.ln2 = nn.LayerNorm(config.n_embd)
        self.mlp = nn.Sequential(
            nn.Linear(config.n_embd, 4 * config.n_embd, bias=False),
            nn.GELU(),
            nn.Linear(4 * config.n_embd, config.n_embd, bias=False),
            nn.Dropout(config.dropout),
        )

    def forward(self, x, cache=None):
        x = x + self.attn(self.ln1(x), cache=cache)
        return x + self.mlp(self.ln2(x))


class CrowGPT(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.token_embedding = nn.Embedding(config.vocab_size, config.n_embd)
        self.position_embedding = nn.Embedding(config.block_size, config.n_embd)
        self.drop = nn.Dropout(config.dropout)
        self.blocks = nn.ModuleList([Block(config) for _ in range(config.n_layer)])
        self.ln_f = nn.LayerNorm(config.n_embd)
        self.head = nn.Linear(config.n_embd, config.vocab_size, bias=False)
        self.head.weight = self.token_embedding.weight

        self.apply(self._init_weights)
        for name, parameter in self.named_parameters():
            if name.endswith("proj.weight") or name.endswith("mlp.2.weight"):
                nn.init.normal_(parameter, mean=0.0, std=0.02 / math.sqrt(2 * config.n_layer))

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

    def empty_cache(self):
        """One [k, v] slot per block. Pass the same list back on every step."""
        return [[] for _ in self.blocks]

    def forward(self, idx, targets=None, legal=None, cache=None, offset=0):
        """`offset` is where `idx` starts in the sequence, for the position
        embedding. It is not derivable from idx.shape once a cache exists: a
        cached step passes ONE token whose true position is the length of the
        history, and defaulting to zero would give every generated token the
        position embedding of the first — which decodes, and is wrong.
        """
        _, time = idx.shape
        positions = torch.arange(offset, offset + time, device=idx.device)
        x = self.drop(self.token_embedding(idx) + self.position_embedding(positions))
        for n, block in enumerate(self.blocks):
            x = block(x, cache=None if cache is None else cache[n])
        logits = self.head(self.ln_f(x))

        if legal is not None:
            logits = logits.masked_fill(legal[:time], float("-inf"))
        if targets is None:
            return logits, None
        loss = F.cross_entropy(
            logits.reshape(-1, logits.size(-1)).float(),
            targets.reshape(-1),
            ignore_index=-1,
        )
        return logits, loss

    def optimiser(self, learning_rate, weight_decay=0.1, betas=(0.9, 0.95)):
        """Decay matmul and embedding weights, never gains and biases."""
        decay, no_decay = [], []
        for parameter in self.parameters():
            if not parameter.requires_grad:
                continue
            (decay if parameter.dim() >= 2 else no_decay).append(parameter)
        return torch.optim.AdamW(
            [
                {"params": decay, "weight_decay": weight_decay},
                {"params": no_decay, "weight_decay": 0.0},
            ],
            lr=learning_rate,
            betas=betas,
        )


class LegalMask:
    """Which token ids may follow each position, as a reusable tensor.

    Kept as [time, vocab] and broadcast over the batch rather than expanded into
    it. At eight codebooks the vocabulary is 8,207 wide, so materialising a
    per-batch copy costs half a gigabyte per step to say something that does not
    depend on the batch at all.
    """

    def __init__(self, vocabulary, block_size, device="cpu"):
        mask = torch.zeros(block_size, vocabulary.size, dtype=torch.bool)
        # The prefix is [species] [call type]? [channel]? [duration], and each
        # slot admits only its own tokens. THE VOCABULARY OWNS THE ORDER — this
        # used to branch on `prefix_len == 3` to decide whether the middle slot
        # was a call type, which stopped being answerable the moment a second
        # optional axis existed, and would have silently admitted a call type
        # where a channel belongs.
        prefix = getattr(vocabulary, "prefix_len", 2)
        slots = vocabulary.prefix_slots()
        for position, (start, end) in enumerate(slots):
            mask[position, start:end] = True
        for position in range(prefix, block_size):
            spans, may_end = vocabulary.allowed(position - prefix)
            for start, end in spans:
                mask[position, start:end] = True
            if may_end:
                mask[position, vocabulary.eos] = True
        self.mask = mask.to(device)
        self.forbidden = ~self.mask

    def legal_count(self, position):
        """How many ids are legal at a position — from the mask, not the GPU."""
        if not hasattr(self, "_counts"):
            self._counts = self.mask.sum(dim=1).cpu().numpy()
        return self._counts[min(position, len(self._counts) - 1)]

    def for_batch(self, time, shift=1):
        """Aligned to what each position predicts, i.e. the NEXT token."""
        return self.forbidden[shift : shift + time]
