"""Training the flow DiT on continuous latents.

THE VALIDATION LOSS HERE IS DETERMINISTIC ON PURPOSE, and it is the one thing
this file gets right that is easy to get wrong. A flow loss depends on a random
timestep and a random noise draw as well as on the data, so an eval that redraws
them measures the dice as much as the model — and `best_val` then records which
step got the friendliest sample. Every eval below uses the SAME frozen (noise, t)
pairs, so two checkpoints are compared on identical questions.

0023 found this project's previous version of the same mistake: `history.json`
was comparing a single dropout-active training minibatch against a 20-batch
eval() mean and reporting negative generalisation gaps. The lesson generalises —
an eval is a measurement, and a measurement with unmanaged randomness in it is
not one.

AND VALIDATION LOSS IS NOT THE TARGET ANYWAY. 0027 trained two identically-sized
models 0.15 nats apart and the listener rated them 1/12 and 1/12; 0023 bought
0.164 nats and measured exactly 0.000 audible difference. Loss is here to detect
a broken run, not to rank checkpoints. Ranking is done by ear, and by 0046's
churn as triage.
"""

import json
import time
from pathlib import Path

import numpy as np
import torch

from crowgpt.continuous import LatentDataset
from crowgpt.flow import Config, FlowDiT, RectifiedFlow


class LatentBatcher:
    """Draws padded, normalised batches of whole bouts.

    `normalisation="global"` CENTRES PER CHANNEL AND SCALES BY ONE NUMBER, and
    that default is a measured correction rather than a preference.

    An RVQ's stages carry naturally decaying variance — measured on this corpus,
    stage 0's channels have 9.9x the spread of stage 31's, stages 0-3 hold 32.7%
    of the total variance and stages 16-31 hold 8.7%. That decay IS the
    perceptual importance ordering: 0024 proved the fine codebooks inaudible by
    ear, and 0035 measured them at 9.935 bits of 10, i.e. near-white.

    Whitening per channel destroys it. Every channel becomes unit variance, so a
    plain MSE spends HALF its loss budget on the sixteen stages that carry 8.7%
    of the signal and are known to be inaudible, and a third on the stages that
    carry structure and pitch. Nothing in a loss curve shows this — it descends
    beautifully while the capacity goes to the wrong place. The first 0054 run
    was trained this way and scored 25.0% against the incumbent's 94.4%.
    """

    def __init__(self, dataset, batch_size, device, seed=0, max_frames=None,
                 normalisation="global"):
        self.dataset = dataset
        self.batch_size = batch_size
        self.device = device
        self.rng = np.random.default_rng(seed)
        self.normalisation = normalisation
        mean, std = dataset.statistics()
        # Guarded because a dead channel with zero spread would divide to inf and
        # take the whole run with it. DAC's upper stages are close to that.
        std = np.maximum(std, 1e-4)
        if normalisation == "global":
            # One scalar, broadcast to [1, dim] so every consumer — including a
            # saved checkpoint's `stats` — stays the same shape either way.
            std = np.full_like(std, float(np.sqrt((std ** 2).mean())))
        elif normalisation != "per_channel":
            raise ValueError(f"unknown normalisation {normalisation!r}")
        self.mean = torch.from_numpy(mean).to(device)
        self.std = torch.from_numpy(std).to(device)
        self.max_frames = max_frames or max(r["frames"] for r in dataset.records)

    def normalise(self, x):
        return (x - self.mean) / self.std

    def denormalise(self, x):
        return x * self.std + self.mean

    def indices(self, count):
        return self.rng.integers(0, len(self.dataset), size=count)

    def batch(self, indices):
        blocks = [np.asarray(self.dataset.latent(i), dtype=np.float32)[: self.max_frames]
                  for i in indices]
        longest = max(b.shape[0] for b in blocks)
        dim = self.dataset.dim
        padded = np.zeros((len(blocks), longest, dim), dtype=np.float32)
        mask = np.zeros((len(blocks), longest), dtype=bool)
        for i, block in enumerate(blocks):
            padded[i, : block.shape[0]] = block
            mask[i, : block.shape[0]] = True
        x = torch.from_numpy(padded).to(self.device)
        pad_mask = torch.from_numpy(mask).to(self.device)
        # Normalise then re-zero the padding, so a padded frame is exactly zero
        # rather than -mean/std. The mask makes it unreachable either way; this
        # keeps it from looking like signal in a debug print.
        x = self.normalise(x) * pad_mask[..., None]
        return x, pad_mask

    def draw(self):
        return self.batch(self.indices(self.batch_size))


class FrozenEval:
    """A fixed set of batches with fixed noise and timesteps."""

    def __init__(self, batcher, batches=16, seed=1234):
        self.batcher = batcher
        rng = np.random.default_rng(seed)
        generator = torch.Generator(device=batcher.device).manual_seed(seed)
        self.items = []
        for _ in range(batches):
            indices = rng.integers(0, len(batcher.dataset), size=batcher.batch_size)
            x, mask = batcher.batch(indices)
            noise = torch.randn(x.shape, device=x.device, generator=generator)
            # UNIFORM t HERE EVEN WHEN TRAINING IS NOT. The eval is a measurement
            # of the model over the whole path, and matching it to the training
            # distribution would make two runs with different `t_sampling`
            # incomparable — each graded on the region it chose to practise.
            t = torch.rand(x.shape[0], device=x.device, generator=generator)
            self.items.append((x, mask, noise, t))

    @torch.no_grad()
    def __call__(self, model):
        model.eval()
        total = 0.0
        for x, mask, noise, t in self.items:
            xt = (1 - t[:, None, None]) * noise + t[:, None, None] * x
            predicted = model(xt, t, pad_mask=mask)
            error = (predicted - (x - noise)) ** 2
            weights = mask[..., None].to(error.dtype)
            total += float((error * weights).sum() / weights.sum().clamp_min(1.0)
                           / error.shape[-1])
        model.train()
        return total / len(self.items)


class FlowTrainer:
    def __init__(self, latent_dir, out_dir, steps=20000, batch_size=32,
                 learning_rate=3e-4, warmup=500, eval_every=500, device=None,
                 config=None, seed=0, normalisation="global",
                 t_sampling="logit_normal", t_mean=-0.5):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if self.device == "cpu":
            raise SystemExit(
                "refusing to train on the CPU — this is hours of work at best and "
                "silently useless at worst. Fix CUDA or pass device explicitly.")
        self.out_dir = Path(out_dir)
        self.steps = steps
        self.eval_every = eval_every
        self.warmup = warmup
        self.learning_rate = learning_rate

        train = LatentDataset(latent_dir, "train")
        val = LatentDataset(latent_dir, "val")
        # ONE FRAME CAP ACROSS BOTH SPLITS. The position embedding is sized from
        # this, and taking it from train alone would crash — or worse, index a
        # row that exists for an unrelated reason — the first time validation
        # happened to hold a longest bout that training did not.
        longest = max(r["frames"] for data in (train, val) for r in data.records)
        self.max_frames = min(longest, 512)
        self.train_batcher = LatentBatcher(train, batch_size, self.device, seed=seed,
                                           max_frames=self.max_frames,
                                           normalisation=normalisation)
        # THE VALIDATION BATCHER TAKES TRAIN'S STATISTICS, not its own. Its own
        # would make the two splits differently scaled and the val loss a
        # measurement of a distribution the model was never fitted to.
        self.val_batcher = LatentBatcher(val, batch_size, self.device, seed=seed + 1,
                                         max_frames=self.max_frames,
                                         normalisation=normalisation)
        self.val_batcher.mean = self.train_batcher.mean
        self.val_batcher.std = self.train_batcher.std
        self.evaluator = FrozenEval(self.val_batcher)
        # A SECOND FROZEN EVAL ON TRAIN, so the generalisation gap is a real one.
        # `history["train"]` is a SINGLE random (t, noise) draw and `val` is a
        # 16-batch frozen mean, so subtracting them compares a noisy sample
        # against an average and produces a "gap" made mostly of variance — which
        # is precisely the bug 0023 found in the incumbent's history.json, where
        # a dropout-active training minibatch was measured against a 20-batch
        # eval() mean and reported NEGATIVE gaps. Same two questions, same
        # frozen noise, or the difference means nothing.
        self.train_evaluator = FrozenEval(self.train_batcher, seed=4321)

        self.config = config or Config(dim=train.dim, max_frames=self.max_frames + 1)
        self.model = FlowDiT(self.config).to(self.device)
        self.flow = RectifiedFlow(self.model, t_sampling=t_sampling, t_mean=t_mean)
        self.optimiser = self.model.optimiser(learning_rate)

    def rate(self, step):
        if step < self.warmup:
            return self.learning_rate * (step + 1) / self.warmup
        progress = (step - self.warmup) / max(1, self.steps - self.warmup)
        return self.learning_rate * (0.5 * (1 + np.cos(np.pi * progress)))

    def save(self, best):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        torch.save({"model": self.model.state_dict(), "config": self.config.as_dict(),
                    "best_val": best,
                    "stats": {"mean": self.train_batcher.mean.cpu().numpy().tolist(),
                              "std": self.train_batcher.std.cpu().numpy().tolist()}},
                   self.out_dir / "model.pt")

    def run(self, on_eval=None, on_step=None):
        """on_eval(step, val) and on_step(step, total) for an unattended runner.

        on_step fires every 25 steps and carries no measurement — it exists
        because the server marks a run stale after 600 s without a write, and at
        eval_every=500 the gap between evals is comfortably inside that window by
        luck rather than design.
        """
        self.model.train()
        history, best, started = [], float("inf"), time.time()

        for step in range(self.steps):
            for group in self.optimiser.param_groups:
                group["lr"] = self.rate(step)

            x, mask = self.train_batcher.draw()
            loss = self.flow.loss(x, pad_mask=mask)
            self.optimiser.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimiser.step()

            if on_step and (step + 1) % 25 == 0:
                on_step(step + 1, self.steps)

            if (step + 1) % self.eval_every == 0 or step + 1 == self.steps:
                val = self.evaluator(self.model)
                train_frozen = self.train_evaluator(self.model)
                history.append({"step": step + 1,
                                # Kept and named honestly: one random draw, high
                                # variance, NOT comparable to `val`.
                                "train_minibatch": loss.detach().item(),
                                "train_frozen": train_frozen, "val": val,
                                "gap": val - train_frozen,
                                "seconds": round(time.time() - started, 1)})
                if val < best:
                    best = val
                    self.save(best)
                if on_eval:
                    on_eval(step + 1, val)
                print(f"   step {step+1:6d}  train {train_frozen:.4f}  val {val:.4f}"
                      f"  gap {val - train_frozen:+.4f}"
                      f"{'  *' if val == best else ''}", flush=True)

        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "history.json").write_text(
            json.dumps({"best_val": best, "history": history}, indent=2))
        return {"best_val": best, "history": history}
