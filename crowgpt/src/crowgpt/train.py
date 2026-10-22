"""Training loop.

Nothing exotic: AdamW, cosine decay, bf16, early stopping on validation loss.
The two things worth knowing are both about not fooling ourselves.

VALIDATION IS BY GROUP. The split already guarantees no recording — and for
American Crow no recordist-day — appears on both sides, so a validation loss
that tracks training loss closely is real evidence of generalisation rather than
of the same bird being scored twice.

AMERICAN CROW IS UPSAMPLED. It is the species this project is about and the
smallest class in the corpus by a factor of four, so on a uniform sampler it
would get the least gradient of the six. The multiplier is applied to the
sampling weights, not by duplicating data, so it cannot leak into the n-gram
index the memorisation check builds.
"""

import json
import math
import os
import time
from pathlib import Path

import numpy as np
import torch

from crowgpt.model import Config, CrowGPT, LegalMask
from crowgpt.tokens import TokenDataset, Vocabulary

AMERICAN_CROW_UPSAMPLE = 3.0


class NoGpu(RuntimeError):
    """CUDA is not usable. There is no fallback, on purpose."""


def require_device():
    """The GPU, or an exception. There is no CPU path.

    `"cuda" if torch.cuda.is_available() else "cpu"` is the line that cost a
    night: something made CUDA unavailable mid-run, this took the else branch,
    and training ran ~240x slower for ten hours while looking merely slow. A
    keyword argument to opt back in was the first fix and it was not good
    enough — an escape hatch is something a future caller passes by accident.

    So there is no argument. The only way to train on the CPU is to set
    CROWGPT_ALLOW_CPU=1 in the environment, which nobody does by accident and
    which announces itself when it happens.

    Availability is not enough, either. It allocates on the device, because
    is_available() has been True on a machine where the first allocation then
    failed, and a driver that reports yes and delivers no is exactly the shape
    of failure this is guarding.
    """
    if os.environ.get("CROWGPT_ALLOW_CPU") == "1":
        print("   CROWGPT_ALLOW_CPU=1 — training on the CPU, ~240x slower. "
              "This is almost certainly not what you want.", flush=True)
        return "cpu"
    if not torch.cuda.is_available():
        raise NoGpu(
            "No CUDA. There is no CPU fallback here — on the CPU a 40-minute "
            "training run takes about a week, and the last time it happened "
            "silently it burned a night.\n"
            "  Check `nvidia-smi`. Set CROWGPT_ALLOW_CPU=1 only if you truly mean it."
        )
    try:
        torch.zeros(1024, device="cuda").sum().item()
    except Exception as exc:  # noqa: BLE001 — any failure here means no GPU
        raise NoGpu(
            f"CUDA reports available but the first allocation failed: "
            f"{type(exc).__name__}: {exc}"
        ) from None
    return "cuda"


def assert_on_gpu(module, where):
    """Confirm the parameters actually landed on the GPU.

    A correct device string is not proof. `.to(device)` can be skipped, a
    submodule can be built after the move, and the result trains at CPU speed
    with every log line still saying cuda.
    """
    if os.environ.get("CROWGPT_ALLOW_CPU") == "1":
        return
    stranded = [n for n, p in module.named_parameters() if p.device.type != "cuda"]
    if stranded:
        raise NoGpu(
            f"{where}: {len(stranded)} parameters are on the CPU "
            f"(e.g. {stranded[0]}) — training would run at CPU speed while "
            f"reporting cuda."
        )

# How hard to flatten the species mix. 0.0 samples in proportion to the corpus,
# 1.0 samples every species equally.
#
# It defaults to 0.0 because that is the decision, not the neutral value. The
# big archive batch makes American Crow ~80% of the corpus and Ben's call was that
# an American Crow model is what he wants — this is the Poe Family's species and
# the one with a strong call-type head. Balancing would spend most of the new
# audio holding five European species up to weight, which is a different project.
# The other five still ride along in proportion; they are just not propped up.
BALANCE = 0.0


class Batcher:
    """Padded batches of whole sequences, with per-species sampling weights."""

    def __init__(self, dataset, batch_size, block_size, device, seed=0, weights=None,
                 vocabulary=None, channels=None, canonical_only=False, keep_groups=None,
                 keep_species=None):
        """`canonical_only` drops the augmented variants, for scoring.

        The train/val "gap" column has never compared like with like: only the
        TRAIN split is augmented (`tokens.TokenWriter.variants`), so a scorer
        reading the train pool draws sequences that are 7/8 sub-hop-shifted and
        gain-attenuated while the validation scorer draws 100% canonical ones.
        That is a difference in data, not in generalisation, and it is why
        several histories on disk carry a NEGATIVE gap — validation looking
        easier than training. 0023 fixed the other half of this (a
        dropout-active minibatch against an eval-mode mean) and left this half
        standing, which matters because its "underfit, unambiguously" verdict
        was read off exactly this column.
        """
        self.dataset = dataset
        self.batch_size = batch_size
        self.block_size = block_size
        self.device = device
        self.rng = np.random.default_rng(seed)
        self.vocabulary = vocabulary
        self.channels = channels
        self.usable = [
            i for i in range(len(dataset))
            if dataset.records[i]["length"] <= block_size + 1
            and (not canonical_only or dataset.records[i].get("canonical", True))
            # SUBSET BY RECORDING GROUP, NEVER BY BOUT. Bouts from one recording
            # are near-duplicates — it is why the split is grouped at all — so
            # thinning bouts would measure "less audio per recording" while the
            # decision in front of us is "more recordings". Unlabelled audio
            # buys recordings.
            and (keep_groups is None or dataset.records[i]["group_key"] in keep_groups)
            and (keep_species is None or dataset.records[i]["species"] in keep_species)
        ]
        if not self.usable:
            raise SystemExit("every sequence is longer than the block size")
        self.probabilities = self._weights(weights)

    def sequence(self, i):
        """The stored sequence, with the channel token spliced in if there is one.

        THE POINT OF DOING IT HERE IS THAT NOTHING HAS TO BE RE-ENCODED. The
        channel is a property of the recording, and every record already carries
        its `recording_id` — so the token can be inserted into the prefix at
        training time and the memmap written by `TokenWriter` stays byte for
        byte what it was. Tokenising the corpus is one to two hours of GPU;
        this is a numpy insert.

        It goes immediately before the duration bucket, because duration has to
        stay the last prefix slot — that is the one `Sampler.tokens` lets the
        model sample.
        """
        stored = self.dataset.sequence(i)
        if not self.channels or not self.vocabulary or not self.vocabulary.channels:
            return stored
        bucket = self.channels.assign(self.dataset.records[i]["recording_id"])
        # The channel slot sits right after species and call type — NOT at
        # prefix_len - 2, which stopped being its address the moment the
        # sampled tail could be two slots long (unit bucket + duration).
        return np.insert(stored, 1 + bool(self.vocabulary.call_types),
                         self.vocabulary.channel_token(bucket))

    def _weights(self, weights):
        if not weights:
            return None
        raw = np.array(
            [weights.get(self.dataset.records[i]["species"], 1.0) for i in self.usable]
        )
        return raw / raw.sum()

    def batch(self):
        picks = self.rng.choice(
            len(self.usable), size=self.batch_size, replace=True, p=self.probabilities
        )
        sequences = [self.sequence(self.usable[p]) for p in picks]
        longest = max(len(s) for s in sequences)

        inputs = np.zeros((len(sequences), longest), dtype=np.int64)
        targets = np.full((len(sequences), longest), -1, dtype=np.int64)
        for i, sequence in enumerate(sequences):
            inputs[i, : len(sequence)] = sequence
            targets[i, : len(sequence) - 1] = sequence[1:]

        return (
            torch.from_numpy(inputs[:, :-1]).to(self.device),
            torch.from_numpy(targets[:, :-1]).to(self.device),
        )


class Trainer:
    def __init__(
        self,
        token_dir,
        out_dir,
        steps=6000,
        batch_size=32,
        learning_rate=3e-4,
        warmup=200,
        eval_every=1000,
        eval_batches=20,
        patience_steps=8000,
        dropout=0.25,
        n_layer=6,
        n_head=4,
        n_embd=256,
        seed=0,
        balance=BALANCE,
        lr_floor=0.1,
        memory_budget=240_000_000,
        accumulate=1,
        block_size=None,
        loss_from_stage=None,
        channels=None,
        keep_groups=None,
        keep_species=None,
        eval_species=None,
    ):
        self.token_dir = Path(token_dir)
        self.out_dir = Path(out_dir)
        self.steps = steps
        self.learning_rate = learning_rate
        self.warmup = warmup
        self.eval_every = eval_every
        self.eval_batches = eval_batches
        # Both were constants in the body until the sweep needed to move them.
        # lr_floor is the fraction of peak the cosine settles at — 0.1 means the
        # schedule never anneals below a tenth and the model spends its last
        # steps still moving. memory_budget is what silently clips the batch: a
        # requested 32 becomes 14 at this block size, which nobody chose.
        self.lr_floor = lr_floor
        self.memory_budget = memory_budget
        # GRADIENT ACCUMULATION EXISTS BECAUSE BATCH SIZE STOPPED BEING A CHOICE
        # AT SIXTEEN CODEBOOKS. The logits tensor is [batch, time, vocab] and
        # both time and vocab double with the codebook count, so it grows
        # fourfold from 6 to 12 kbps: the standing d384/L8 shape fits a micro
        # batch of 6 on a 16 GB card and OOMs at 8, against the 16 the incumbent
        # model-d384-6k actually trained with. Without this, a bandwidth
        # comparison is also a batch-size comparison, and 0023 already showed
        # batch size moves the result on its own.
        self.accumulate = max(1, int(accumulate))
        # THE EXTENDER'S ONE KNOB. With loss_from_stage=8 the model still
        # SEES every token, so each fine stage is predicted from the complete
        # same-frame coarse context; it is only scored on stages at or above
        # the cut. Coarse tokens become pure conditioning, which is exactly
        # the job at inference, where real or generated coarse codes are fed
        # in and only the fine stages are sampled.
        self.loss_from_stage = loss_from_stage
        # TRAIN ONLY. The validation split stays whole across every arm of a
        # scaling curve, or the losses are not comparable — a smaller val set is
        # a different question, not a smaller answer to the same one.
        self.keep_groups = keep_groups
        # TRAIN AND VALIDATION FILTER SEPARATELY, and they must. A multilingual
        # arm trains on 46 species and a monolingual one on 1, but both have to
        # be SCORED on the same held-out American Crow or the losses answer
        # different questions — arm B's would be an average over 46 species and
        # would look better or worse for reasons that have nothing to do with
        # American Crow.
        self.keep_species = keep_species
        self.eval_species = eval_species
        # PATIENCE IS IN STEPS. It used to be a count of evaluations, which made
        # it silently depend on eval_every: the run that produced the best model
        # so far allowed 8,000 stale steps (patience 8 at eval_every 1000), and
        # the overnight defaults allowed 1,500 (patience 6 at eval_every 250).
        # Four times stricter, from a parameter that looks unrelated, and every
        # model in the ladder stopped at a quarter of its steps because of it.
        # That best model found its best validation loss at step 19,000.
        self.patience_steps = patience_steps
        self.patience = max(1, patience_steps // max(1, eval_every))
        self.device = require_device()

        torch.manual_seed(seed)
        self.train_set = TokenDataset(token_dir, "train")
        self.val_set = TokenDataset(token_dir, "val")
        manifest = self.train_set.manifest

        # The cap has to clear the longest sequence the codec can produce, and
        # that scales with the codebook count: a 3-second bout is 1,803 tokens
        # at eight codebooks and 3,603 at sixteen. A 2,048 cap silently excluded
        # most of the corpus at 12 kbps — the Batcher drops anything longer than
        # the block, so the run trained on short bouts only and said nothing.
        # `channels` is a ChannelBuckets, or None for the unconditioned model.
        # Its names go into the vocabulary and its assignment goes into the
        # prefix at batch time, so a channel-conditioned run reads exactly the
        # same token directory as an unconditioned one — see Batcher.sequence.
        self.channels = channels
        self.vocabulary = Vocabulary(manifest["n_codebooks"], manifest["species"],
                                     manifest.get("call_types", ()),
                                     channels.names if channels else (),
                                     n_unit_buckets=manifest.get("n_unit_buckets", 0))
        # The spliced token makes every sequence one longer than it is on disk,
        # and the block has to clear it or Batcher drops the longest bouts
        # without saying so.
        longest = max(r["length"] for r in self.train_set.records) + bool(channels)
        # THE 4096 CAP WAS A CONSTANT UNTIL 24 CODEBOOKS NEEDED MORE. A 3-second
        # bout is 1,803 tokens at eight and 5,404 at twenty-four, and Batcher
        # silently DROPS anything longer than the block — at 24 codebooks a 4,096
        # cap keeps 57% of the corpus and says nothing about the rest. Measured
        # retention: 4,096 keeps 100% at K=16, 57% at K=24, 40% at K=32; 6,144
        # keeps 100% through K=24; 8,192 is needed for K=32.
        block_cap = block_size or 4096
        block_size = int(min(block_cap, max(256, longest)))
        self.config = Config(
            vocab_size=self.vocabulary.size,
            n_codebooks=manifest["n_codebooks"],
            block_size=block_size,
            n_layer=n_layer,
            n_head=n_head,
            n_embd=n_embd,
            dropout=dropout,
            prefix_len=self.vocabulary.prefix_len,
        )
        self.model = CrowGPT(self.config).to(self.device)
        assert_on_gpu(self.model, "the model")
        self.legal = LegalMask(self.vocabulary, block_size + 1, self.device)

        # Logits are [batch, time, vocab], and both time and vocab double when
        # the codebook count does, so the loss tensor grows fourfold between
        # 6 and 12 kbps. Size the batch to hold that roughly constant rather
        # than picking a number that only happens to fit at one bandwidth.
        budget = self.memory_budget
        per_sample = block_size * self.config.vocab_size
        batch_size = int(max(2, min(batch_size, budget // per_sample)))
        self.micro_batch = batch_size
        self.effective_batch = batch_size * self.accumulate

        weights = self._species_weights(manifest["species"], balance)
        self.species_mix = weights
        self.train_batcher = Batcher(
            self.train_set, batch_size, block_size, self.device, seed, weights,
            vocabulary=self.vocabulary, channels=channels, keep_groups=keep_groups,
            keep_species=keep_species
        )
        # Counted against what the block size alone would have kept, so a
        # deliberate `keep_groups` subset is not reported as sequences too long.
        # The warning exists to catch a silently truncated corpus; blaming the
        # block for a subset the caller asked for would make it noise.
        in_block = sum(1 for r in self.train_set.records if r["length"] <= block_size + 1)
        dropped = in_block - len(self.train_batcher.usable) if keep_groups is None \
            else len(self.train_set) - in_block
        if dropped:
            share = dropped / max(1, len(self.train_set))
            print(f"   WARNING: {dropped} sequences ({share:.1%}) exceed the "
                  f"{block_size}-token block and will not be trained on", flush=True)
        self.val_batcher = Batcher(
            self.val_set, batch_size, block_size, self.device, seed + 1,
            vocabulary=self.vocabulary, channels=channels,
            keep_species=eval_species
        )
        # A THIRD BATCHER, over the training split, used only for scoring. The
        # training number in every history.json so far was `loss.item()` from a
        # single minibatch with dropout still active, compared against a
        # 20-batch mean under eval(). That is not a gap, it is two different
        # measurements, and it is why several of them came out negative. This
        # one is drawn like the validation batcher so the two are comparable.
        # It carries its own seed so scoring cannot perturb the order training
        # sees.
        self.eval_train_batcher = Batcher(
            self.train_set, batch_size, block_size, self.device, seed + 2, weights,
            vocabulary=self.vocabulary, channels=channels, canonical_only=True,
            keep_groups=keep_groups, keep_species=keep_species
        )

    def _species_weights(self, species, balance):
        """Per-sequence sampling weights, from the corpus mix and the dial.

        At balance=0 every sequence is equally likely, so species appear in
        proportion to how much audio each has. At balance=1 each species gets an
        equal share whatever its size.
        """
        counts = {slug: 0 for slug in species}
        for record in self.train_set.records:
            counts[record["species"]] = counts.get(record["species"], 0) + 1
        total = sum(counts.values()) or 1
        weights = {}
        for slug, count in counts.items():
            share = (count or 1) / total
            weights[slug] = share ** (-balance)
        # The old upsample only made sense while American Crow was the SMALLEST
        # class — 173 recordings against 500 each. The big archive batch inverted that, so it
        # now applies only if the corpus somehow reverts to that shape.
        if balance < 1.0 and counts.get("american-crow"):
            smallest = min(c for c in counts.values() if c)
            if counts["american-crow"] <= smallest * 1.5:
                weights["american-crow"] *= AMERICAN_CROW_UPSAMPLE
        return weights

    def _learning_rate(self, step):
        if step < self.warmup:
            return self.learning_rate * (step + 1) / self.warmup
        progress = (step - self.warmup) / max(1, self.steps - self.warmup)
        floor = self.lr_floor
        return floor * self.learning_rate + (1 - floor) * self.learning_rate * 0.5 * (
            1 + math.cos(math.pi * min(1.0, progress))
        )

    def _mask_coarse(self, targets):
        """Blank the targets below `loss_from_stage`, leaving EOS and prefix.

        Stage comes from the token id, not from counting positions: codec id j
        occupies [j*1024, (j+1)*1024), so `id // 1024` is self-verifying, and
        position arithmetic would have to know the prefix length.

        EOS AND PREFIX SURVIVE BY CONSTRUCTION, which is worth stating because it
        is not obvious and is silent if wrong. `Vocabulary` puts EOS at exactly
        CODEBOOK_SIZE * n_codebooks and the prefix above it, so their `id // 1024`
        is >= n_codebooks, which is >= any legal cut. Padding is already -1 and
        floor-divides to -1, so it stays masked.
        """
        if not self.loss_from_stage:
            return targets
        from crowgpt.codec import CODEBOOK_SIZE

        keep = targets.clone()
        codec = (targets >= 0) & (targets < self.vocabulary.codec_size)
        keep[codec & (targets // CODEBOOK_SIZE < self.loss_from_stage)] = -1
        return keep

    def _loss(self, inputs, targets):
        targets = self._mask_coarse(targets)
        legal = self.legal.for_batch(inputs.size(1), shift=1)
        with torch.autocast(self.device, dtype=torch.bfloat16, enabled=self.device == "cuda"):
            _, loss = self.model(inputs, targets, legal)
        return loss

    @torch.no_grad()
    def evaluate(self):
        """Both splits, same conditions, so the difference is a real gap.

        Returns (train, val). Under eval() with dropout off and the same number
        of batches on each side, which is the whole point: the old training
        figure was one dropout-active minibatch and could not be subtracted from
        anything. Twenty extra forward passes per eval, under 1% of runtime, and
        it is the only measurement that can say whether the model is underfit.
        """
        self.model.eval()
        val = [self._loss(*self.val_batcher.batch()).item() for _ in range(self.eval_batches)]
        train = [self._loss(*self.eval_train_batcher.batch()).item()
                 for _ in range(self.eval_batches)]
        self.model.train()
        return float(np.mean(train)), float(np.mean(val))

    def run(self, on_eval=None, on_step=None):
        """on_eval(step, val_loss) lets an unattended runner report progress.

        on_step(step, total) fires far more often and carries no measurement.
        Evaluation is expensive enough to be rare — at eval_every=500 and about
        a second a step that is nine minutes between updates, which on a
        five-hour stage is long enough for the dashboard to look hung.
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)
        optimiser = self.model.optimiser(self.learning_rate)
        print(
            f"   {self.model.n_params()/1e6:.1f}M params · block {self.config.block_size} · "
            f"{len(self.train_set)} train / {len(self.val_set)} val sequences",
            flush=True,
        )
        print(f"   batch {self.effective_batch} "
              f"({self.micro_batch} x {self.accumulate} accumulated)", flush=True)
        print(f"   early stop after {self.patience_steps} stale steps "
              f"({self.patience} evals at every {self.eval_every})", flush=True)
        mix = " ".join(f"{s}={w:.2f}" for s, w in sorted(self.species_mix.items()))
        print(f"   sampling weights: {mix}", flush=True)

        history, best, stale = [], float("inf"), 0
        started = time.time()
        for step in range(self.steps):
            for group in optimiser.param_groups:
                group["lr"] = self._learning_rate(step)
            optimiser.zero_grad(set_to_none=True)
            for micro in range(self.accumulate):
                inputs, targets = self.train_batcher.batch()
                if step == 0 and micro == 0:
                    assert_on_gpu(self.model, "the model at step 0")
                    if inputs.device.type != self.device:
                        raise NoGpu(f"batches are on {inputs.device.type}, not {self.device}")
                # Divided, not summed: without this the gradient is the sum of
                # the micro-batches, which is a silent learning-rate multiply by
                # the accumulation factor and makes every carried-over
                # hyperparameter wrong by that factor.
                loss = self._loss(inputs, targets) / self.accumulate
                loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            optimiser.step()

            if on_step and (step + 1) % 25 == 0:
                on_step(step + 1, self.steps)

            if (step + 1) % self.eval_every == 0 or step == self.steps - 1:
                train_loss, val = self.evaluate()
                history.append({
                    "step": step + 1,
                    "train": round(train_loss, 4),
                    "val": round(val, 4),
                    "gap": round(val - train_loss, 4),
                    # Kept because it is what every earlier history recorded, so
                    # old and new runs can still be lined up — but it is a single
                    # dropout-active minibatch and is not the training loss.
                    "train_minibatch": round(loss.item(), 4),
                })
                print(
                    f"   step {step+1:5d}  train {train_loss:.4f}  val {val:.4f}  "
                    f"gap {val - train_loss:+.4f}  {time.time()-started:.0f}s",
                    flush=True,
                )
                if on_eval:
                    on_eval(step + 1, val)
                if val < best - 1e-4:
                    best, stale = val, 0
                    self.save(step + 1, val)
                else:
                    stale += 1
                    if stale >= self.patience:
                        print("   early stop", flush=True)
                        break

        (self.out_dir / "history.json").write_text(
            json.dumps({"best_val": best, "history": history}, indent=2)
        )
        return {"best_val": best, "history": history}

    def save(self, step, val):
        # The channel names go in the MANIFEST COPY, not the token directory's
        # manifest on disk: the token set is shared by conditioned and
        # unconditioned runs and describes what was encoded, while the channel
        # list describes what this checkpoint was trained with. Writing it back
        # to the shared file would tell an unconditioned model it has channels.
        manifest = dict(self.train_set.manifest)
        if self.channels:
            manifest["channels"] = self.vocabulary.channels
            manifest["vocab_size"] = self.vocabulary.size
        torch.save(
            {
                "model": self.model.state_dict(),
                "config": self.config.as_dict(),
                "manifest": manifest,
                "step": step,
                "val_loss": val,
            },
            self.out_dir / "model.pt",
        )
