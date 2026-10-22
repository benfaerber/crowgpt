"""A rectified-flow DiT over continuous DAC latents.

WHAT IS DIFFERENT FROM `model.py`, and it is not the architecture. The incumbent
predicts a codebook INDEX with a 1024-way softmax, so every frame is either right
or wrong and a wrong one is a blip. This predicts a VELOCITY in a continuous
space, where being close is a partial success — and 0052 measured how close is
close enough: 20% of a channel's spread is inaudible (10/25, below chance),
against 21/25 at 80%.

THREE MEASURED DEFECTS THIS IS AIMED AT.

  0046: stage-0 churn is 0.801 generated against 0.868 real, and only the coarse
  book that carries structure and pitch is sticky. Cross-entropy pays a symbol
  model to hold the modal code; a velocity field has no mode to collapse onto and
  no top-k to flatten it.

  Ben, repeatedly: "a single blip", "either pretty good or pretty bad". That is
  autoregressive exposure bias — a committed token cannot be revised. Every step
  here sees the whole bout, so a locally implausible frame is corrected by the
  next step rather than conditioning everything after it.

  0035: DAC's fine stages carry 9.935 bits of 10 AS SYMBOLS and no capacity
  extracts them. As vectors they are a small residual, and a flow model asked for
  a near-white residual produces smooth noise of the right magnitude instead of
  an independent 1024-way draw per frame, which is what a modem sounds like.

SEQUENCE LENGTH IS THE OTHER HALF. DAC-24 at 24 codebooks is transparent (0039,
ABX 0.522) and costs 5,400 tokens for a 3-second bout, which no autoregressive
model here can afford — so the generator has been stuck at k=8, the setting Ben
calls the robot problem. The same three seconds is 225 positions of a 256-d
vector. Full transparent fidelity, shorter than what the incumbent already runs.

CONVENTION: x0 is noise, x1 is data, xt = (1-t)*x0 + t*x1, and the model predicts
the velocity x1 - x0. Sampling integrates that field from t=0 to t=1. Written down
because half the sign errors in flow matching are a reversed time axis, and they
produce output that looks trained and sounds like noise.
"""

import math

import torch
import torch.nn as nn
from torch.nn import functional as F


class Config:
    def __init__(self, dim=256, n_layer=8, n_head=6, n_embd=384, dropout=0.0,
                 max_frames=256):
        self.dim = dim
        self.n_layer = n_layer
        self.n_head = n_head
        self.n_embd = n_embd
        self.dropout = dropout
        self.max_frames = max_frames

    def as_dict(self):
        return dict(self.__dict__)


def timestep_embedding(t, width, max_period=10000):
    half = width // 2
    freqs = torch.exp(
        -math.log(max_period) * torch.arange(half, device=t.device, dtype=torch.float32) / half)
    args = t.float()[:, None] * freqs[None]
    return torch.cat([torch.cos(args), torch.sin(args)], dim=-1)


class Modulation(nn.Module):
    """adaLN-Zero: the timestep sets scale, shift and gate for one sublayer.

    ZERO-INITIALISED ON PURPOSE. Every block starts as the identity, so an
    untrained model returns its input unchanged rather than noise, and depth
    costs nothing at initialisation. Without it a deep DiT spends its first
    thousand steps undoing its own initialisation.
    """

    def __init__(self, n_embd, n_params):
        super().__init__()
        self.net = nn.Sequential(nn.SiLU(), nn.Linear(n_embd, n_params * n_embd))
        nn.init.zeros_(self.net[1].weight)
        nn.init.zeros_(self.net[1].bias)
        self.n_params = n_params

    def forward(self, conditioning):
        return self.net(conditioning).chunk(self.n_params, dim=-1)


class SelfAttention(nn.Module):
    """Bidirectional. There is no causal mask anywhere in this file.

    That is the point of the whole approach — the model may look forward as well
    as back, which is what lets a bad frame be repaired by context that has not
    happened yet. A causal mask here would reintroduce exactly the constraint
    this exists to remove.
    """

    def __init__(self, config):
        super().__init__()
        self.n_head = config.n_head
        self.n_embd = config.n_embd
        self.qkv = nn.Linear(config.n_embd, 3 * config.n_embd, bias=False)
        self.proj = nn.Linear(config.n_embd, config.n_embd, bias=False)
        self.dropout = config.dropout

    def forward(self, x, pad_mask=None):
        batch, time, channels = x.shape
        q, k, v = self.qkv(x).split(self.n_embd, dim=2)
        shape = (batch, time, self.n_head, channels // self.n_head)
        q, k, v = (t.view(*shape).transpose(1, 2) for t in (q, k, v))

        attn_mask = None
        if pad_mask is not None:
            # [B, 1, 1, T] — padding is not attendable. Without this a short bout
            # in a long batch attends to its own zero padding, which is a real
            # frame as far as attention is concerned and pulls every latent
            # toward zero at the tail.
            attn_mask = pad_mask[:, None, None, :]

        out = F.scaled_dot_product_attention(
            q, k, v, attn_mask=attn_mask,
            dropout_p=self.dropout if self.training else 0.0)
        return self.proj(out.transpose(1, 2).contiguous().view(batch, time, channels))


class Block(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.n_embd, elementwise_affine=False)
        self.attn = SelfAttention(config)
        self.ln2 = nn.LayerNorm(config.n_embd, elementwise_affine=False)
        self.mlp = nn.Sequential(
            nn.Linear(config.n_embd, 4 * config.n_embd),
            nn.GELU(),
            nn.Linear(4 * config.n_embd, config.n_embd),
        )
        self.modulation = Modulation(config.n_embd, 6)

    def forward(self, x, conditioning, pad_mask=None):
        shift1, scale1, gate1, shift2, scale2, gate2 = self.modulation(conditioning)
        h = self.ln1(x) * (1 + scale1[:, None]) + shift1[:, None]
        x = x + gate1[:, None] * self.attn(h, pad_mask=pad_mask)
        h = self.ln2(x) * (1 + scale2[:, None]) + shift2[:, None]
        return x + gate2[:, None] * self.mlp(h)


class FlowDiT(nn.Module):
    """Predicts the flow velocity at (x_t, t) for a whole bout at once."""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.input = nn.Linear(config.dim, config.n_embd)
        self.position = nn.Embedding(config.max_frames, config.n_embd)
        self.time = nn.Sequential(
            nn.Linear(config.n_embd, config.n_embd), nn.SiLU(),
            nn.Linear(config.n_embd, config.n_embd))
        self.blocks = nn.ModuleList([Block(config) for _ in range(config.n_layer)])
        self.ln_f = nn.LayerNorm(config.n_embd, elementwise_affine=False)
        self.final_modulation = Modulation(config.n_embd, 2)
        self.output = nn.Linear(config.n_embd, config.dim)
        nn.init.zeros_(self.output.weight)
        nn.init.zeros_(self.output.bias)

    def n_params(self):
        return sum(p.numel() for p in self.parameters())

    def forward(self, x, t, pad_mask=None):
        _, frames, _ = x.shape
        positions = torch.arange(frames, device=x.device)
        h = self.input(x) + self.position(positions)[None]
        conditioning = self.time(timestep_embedding(t, self.config.n_embd))
        for block in self.blocks:
            h = block(h, conditioning, pad_mask=pad_mask)
        shift, scale = self.final_modulation(conditioning)
        return self.output(self.ln_f(h) * (1 + scale[:, None]) + shift[:, None])

    def optimiser(self, learning_rate, weight_decay=0.01, betas=(0.9, 0.95)):
        decay, no_decay = [], []
        for parameter in self.parameters():
            if parameter.requires_grad:
                (decay if parameter.dim() >= 2 else no_decay).append(parameter)
        return torch.optim.AdamW(
            [{"params": decay, "weight_decay": weight_decay},
             {"params": no_decay, "weight_decay": 0.0}],
            lr=learning_rate, betas=betas)


class RectifiedFlow:
    """The objective and the sampler, kept together so their conventions cannot drift."""

    def __init__(self, model, t_sampling="uniform", t_mean=-0.5, t_std=1.0):
        """`t_sampling` decides where along the path the training signal goes.

        UNIFORM UNDER-TRAINS THE END THAT MATTERS, and 0054 measured it rather
        than inheriting it from a paper. Starting the ODE from a real latent
        partially noised, the first model reconstructed to 100% BirdNET detection
        at confidence 0.919 from t=0.5 — above real audio's 0.749 — and collapsed
        to 8.3% from t=0.0. The velocity field is right; what is missing is the
        earliest, noise-dominated stretch where global structure is decided. The
        model can refine and cannot originate.

        Uniform t spends the same budget on t=0.9, where the answer is nearly
        given, as on t=0.05, where it has to be invented. `logit_normal` draws
        t = sigmoid(N(mean, std)), and a NEGATIVE mean pulls mass toward the
        noise end. Note the sign convention is this file's, not SD3's: here t=0
        is noise and t=1 is data, so their positive shift is this one's negative.
        """
        self.model = model
        self.t_sampling = t_sampling
        self.t_mean = t_mean
        self.t_std = t_std

    def timesteps(self, batch, device, generator=None):
        if self.t_sampling == "uniform":
            return torch.rand(batch, device=device, generator=generator)
        if self.t_sampling == "logit_normal":
            normal = torch.randn(batch, device=device, generator=generator)
            return torch.sigmoid(normal * self.t_std + self.t_mean)
        raise ValueError(f"unknown t_sampling {self.t_sampling!r}")

    def loss(self, x1, pad_mask=None, generator=None):
        """x1 is normalised data [B, T, C]. Returns the masked velocity MSE."""
        batch = x1.shape[0]
        noise = torch.randn(x1.shape, device=x1.device, generator=generator)
        t = self.timesteps(batch, x1.device, generator=generator)
        xt = (1 - t[:, None, None]) * noise + t[:, None, None] * x1
        target = x1 - noise
        predicted = self.model(xt, t, pad_mask=pad_mask)

        error = (predicted - target) ** 2
        if pad_mask is None:
            return error.mean()
        # Mean over REAL frames only. Averaging over padding makes a batch of
        # short bouts look easy and rewards predicting zero.
        weights = pad_mask[..., None].to(error.dtype)
        return (error * weights).sum() / weights.sum().clamp_min(1.0) / error.shape[-1]

    @torch.no_grad()
    def sample(self, frames, count=1, steps=32, device="cuda", generator=None, guidance=None):
        """Integrate the velocity field from noise to data with Euler steps."""
        shape = (count, frames, self.model.config.dim)
        x = torch.randn(shape, device=device, generator=generator)
        times = torch.linspace(0.0, 1.0, steps + 1, device=device)
        for i in range(steps):
            t = times[i].expand(count)
            velocity = self.model(x, t)
            x = x + velocity * (times[i + 1] - times[i])
        return x
