"""Where the model's uncertainty actually lives, split by residual codebook.

ONE FLAT CROSS-ENTROPY REPORTS A SINGLE NUMBER FOR EIGHT DIFFERENT PROBLEMS.
Training averages the loss over every position, so 4.71 nats is equally
consistent with a model that has learnt the coarse codebook and given up on the
fine ones, and with a model that is mediocre at all eight. Those want opposite
fixes and nothing on disk can separate them: `history.json` holds a best value
and a two-column curve.

THE QUESTION THIS EXISTS TO ANSWER. Generation uses one temperature for the
whole stream, and the history of that constant is a fight it cannot win — 0.95,
then 1.15, then 1.0, each measured and each right about something. Raising it
shortens bouts and flattens their contour; lowering it grits the texture and
drives n-gram overlap to nine times the held-out base rate. The suspicion is
that the knob is aliasing two jobs: the coarse stage carries structure, duration
and contour, while the fine residual stages carry texture, and a model that is
blurry only at the fine end wants them cooled separately.

THIS MEASURES WHETHER THAT IS TRUE, AND IT CAN REFUTE IT. Two outcomes kill the
idea before any sampler code is written:

  - Flat calibration. If the per-stage temperature that minimises held-out loss
    is the same at every stage, a per-stage schedule is a global one in a
    costume.
  - Correct uncertainty. If a fine stage's cross-entropy already equals its own
    predictive entropy and both sit at the codec's marginal, the model is not
    blurry there — the residual is genuinely unpredictable given the context.
    Cooling a correctly-uncertain distribution does not clean it up; it makes
    the sampler re-pick the same arbitrary residual code over and over, which is
    periodic, and periodic is what "robotic" sounds like. THIS IS THE OUTCOME TO
    WATCH FOR, because high fine-stage entropy feels like confirmation while
    being the opposite.

The null is on disk already. Experiment 0014 measured the codec's own per-stage
marginal entropy on gated windows at [6.30, 7.06, 7.34, 7.50, 7.63, 7.73, 7.80,
7.84] bits of a possible 10. No stage is noise, and the whole spread is 1.5
bits — so a model whose per-stage spread is much larger than that is failing on
its own account rather than inheriting the tokenizer's shape.

Stages come from the target token id, not from counting positions. Codec ids are
laid out with stage `j` occupying `[j*1024, (j+1)*1024)`, so `id // 1024` is
self-verifying; position arithmetic would have to know the prefix length, which
is no longer a constant now that a call-type token can sit between species and
duration.
"""

import numpy as np
import torch
from torch.nn import functional as F

from crowgpt.codec import CODEBOOK_SIZE
from crowgpt.model import LegalMask

CODEC_MARGINAL_BITS = (6.30, 7.06, 7.34, 7.50, 7.63, 7.73, 7.80, 7.84)
TEMPERATURE_GRID = tuple(np.round(np.arange(0.60, 1.61, 0.05), 2))
NATS_TO_BITS = 1.0 / np.log(2.0)


class Batches:
    """Padded batches that also say which species each sequence came from.

    `train.Batcher` drops that on the floor, and train.py is off limits while it
    carries uncommitted work and a running job, so this keeps its own copy of
    twenty lines rather than reaching across.
    """

    def __init__(self, dataset, batch_size, block_size, device, seed=0):
        self.dataset = dataset
        self.batch_size = batch_size
        self.block_size = block_size
        self.device = device
        self.rng = np.random.default_rng(seed)
        self.usable = [
            i for i in range(len(dataset)) if dataset.records[i]["length"] <= block_size + 1
        ]
        if not self.usable:
            raise SystemExit("every sequence is longer than the block size")

    def __iter__(self):
        order = self.rng.permutation(len(self.usable))
        for start in range(0, len(order) - self.batch_size + 1, self.batch_size):
            picks = [self.usable[i] for i in order[start : start + self.batch_size]]
            yield self._assemble(picks)

    def _assemble(self, picks):
        sequences = [self.dataset.sequence(i) for i in picks]
        species = [self.dataset.records[i]["species"] for i in picks]
        longest = max(len(s) for s in sequences)

        inputs = np.zeros((len(sequences), longest), dtype=np.int64)
        targets = np.full((len(sequences), longest), -1, dtype=np.int64)
        for i, sequence in enumerate(sequences):
            inputs[i, : len(sequence)] = sequence
            targets[i, : len(sequence) - 1] = sequence[1:]

        return (
            torch.from_numpy(inputs[:, :-1]).to(self.device),
            torch.from_numpy(targets[:, :-1]).to(self.device),
            species,
        )


class StageProfile:
    """Held-out loss, entropy and calibration for every residual stage."""

    def __init__(self, model, vocabulary, dataset, device="cpu", batch_size=4, batches=16,
                 block_size=None, seed=0):
        self.model = model.to(device).eval()
        self.vocabulary = vocabulary
        self.device = device
        self.batches = batches
        self.block_size = block_size or model.config.block_size
        self.legal = LegalMask(vocabulary, self.block_size + 1, device)
        self.source = Batches(dataset, batch_size, self.block_size, device, seed)

    @torch.no_grad()
    def measure(self):
        stages = self.vocabulary.n_codebooks
        loss_sum = np.zeros(stages + 1)
        entropy_sum = np.zeros(stages + 1)
        counts = np.zeros(stages + 1)
        grid_sum = np.zeros((stages + 1, len(TEMPERATURE_GRID)))
        per_species = {}
        eos_ranks = {"ending": [], "mid": []}

        for index, (inputs, targets, species) in enumerate(self.source):
            if index >= self.batches:
                break
            logits, _ = self.model(inputs)
            logits = logits.float().masked_fill(
                self.legal.for_batch(inputs.size(1), shift=1), float("-inf")
            )

            flat_logits = logits.reshape(-1, logits.size(-1))
            flat_targets = targets.reshape(-1)
            keep = flat_targets >= 0
            flat_logits, flat_targets = flat_logits[keep], flat_targets[keep]

            bucket = self._bucket(flat_targets, stages)
            losses = F.cross_entropy(flat_logits, flat_targets, reduction="none")
            probabilities = torch.softmax(flat_logits, dim=-1)
            entropies = -(probabilities * torch.log(probabilities.clamp_min(1e-12))).sum(-1)

            counts += np.bincount(bucket.cpu().numpy(), minlength=stages + 1)
            loss_sum += self._by_bucket(losses, bucket, stages)
            entropy_sum += self._by_bucket(entropies, bucket, stages)
            for column, temperature in enumerate(TEMPERATURE_GRID):
                scaled = F.cross_entropy(
                    flat_logits / temperature, flat_targets, reduction="none"
                )
                grid_sum[:, column] += self._by_bucket(scaled, bucket, stages)

            self._add_species(per_species, losses, targets, keep, species)
            for where, ranks in self._eos_ranks(flat_logits, flat_targets).items():
                eos_ranks[where].extend(ranks)

        return self._summarise(loss_sum, entropy_sum, counts, grid_sum, per_species, eos_ranks)

    @staticmethod
    def _by_bucket(values, bucket, stages):
        totals = torch.zeros(stages + 1, dtype=torch.float64, device=values.device)
        return totals.index_add_(0, bucket, values.double()).cpu().numpy()

    def _bucket(self, targets, stages):
        """Stage from the id; everything non-codec lands in one trailing slot."""
        bucket = torch.full_like(targets, stages)
        codec = targets < self.vocabulary.codec_size
        bucket[codec] = targets[codec] // CODEBOOK_SIZE
        return bucket

    def _add_species(self, into, losses, targets, keep, species):
        rows = torch.arange(targets.size(0), device=targets.device)
        rows = rows.unsqueeze(1).expand_as(targets).reshape(-1)[keep]
        for i, slug in enumerate(species):
            mask = rows == i
            if not bool(mask.any()):
                continue
            total, n = into.setdefault(slug, [0.0, 0])
            into[slug] = [total + float(losses[mask].sum()), n + int(mask.sum())]

    def _eos_ranks(self, logits, targets):
        """How far down the ordering EOS sits where it is legal.

        `top_k=200` keeps the two hundred best ids, so an EOS ranked below that
        cannot be emitted at all. THE POOLED RANK IS NOT THE INTERESTING NUMBER
        AND IS EASY TO MISREAD: a 2.2 s bout has about 165 frame boundaries and
        only one of them is the end, so a model that ranked EOS highly at all of
        them would be broken. What matters is the rank at the boundary where the
        bout actually does stop — if EOS falls outside the kept set THERE, the
        sampler is structurally unable to end the bout and must overrun.

        So the two are separated: `ending`, where the true next token is EOS,
        and `mid`, where it is not.
        """
        boundaries = torch.isfinite(logits[:, self.vocabulary.eos])
        if not bool(boundaries.any()):
            return {"ending": [], "mid": []}
        rows = logits[boundaries]
        wanted = targets[boundaries] == self.vocabulary.eos
        eos = rows[:, self.vocabulary.eos].unsqueeze(1)
        ranks = (rows > eos).sum(dim=1)
        return {
            "ending": ranks[wanted].cpu().numpy().tolist(),
            "mid": ranks[~wanted].cpu().numpy().tolist(),
        }

    def _summarise(self, loss_sum, entropy_sum, counts, grid_sum, per_species, eos_ranks):
        stages = self.vocabulary.n_codebooks
        rows = []
        for stage in range(stages):
            if not counts[stage]:
                continue
            loss_bits = loss_sum[stage] / counts[stage] * NATS_TO_BITS
            entropy_bits = entropy_sum[stage] / counts[stage] * NATS_TO_BITS
            marginal = (CODEC_MARGINAL_BITS[stage]
                        if stage < len(CODEC_MARGINAL_BITS) else float("nan"))
            best = int(np.argmin(grid_sum[stage]))
            rows.append({
                "stage": stage,
                "n": int(counts[stage]),
                "cross_entropy_bits": round(loss_bits, 4),
                "predictive_entropy_bits": round(entropy_bits, 4),
                "marginal_bits": marginal,
                "bits_recovered": round(marginal - loss_bits, 4),
                "overconfidence": round(loss_bits - entropy_bits, 4),
                "calibration_t": float(TEMPERATURE_GRID[best]),
            })

        prefix = {}
        if counts[stages]:
            prefix = {
                "n": int(counts[stages]),
                "cross_entropy_bits": round(loss_sum[stages] / counts[stages] * NATS_TO_BITS, 4),
                "calibration_t": float(TEMPERATURE_GRID[int(np.argmin(grid_sum[stages]))]),
            }

        return {
            "stages": rows,
            "prefix": prefix,
            "species": {
                slug: round(total / n * NATS_TO_BITS, 4)
                for slug, (total, n) in sorted(per_species.items())
            },
            "eos": self._eos_summary(eos_ranks),
            "verdict": self.verdict(rows),
        }

    def _eos_summary(self, ranks):
        out = {}
        for where, values in ranks.items():
            if not values:
                continue
            values = np.array(values)
            out[where] = {
                "n": int(values.size),
                "median_rank": float(np.median(values)),
                "inside_top_200": round(float((values < 200).mean()), 4),
            }
        return out

    @staticmethod
    def verdict(rows):
        """The pre-registered reading, decided before the numbers existed."""
        if len(rows) < 2:
            return "no data"
        temperatures = [row["calibration_t"] for row in rows]
        if max(temperatures) - min(temperatures) <= 0.03:
            return ("flat calibration — a per-stage temperature is a global one in a "
                    "costume, and the idea is dead")

        fine = [row for row in rows if row["stage"] >= len(rows) // 2]
        correctly_uncertain = all(
            abs(row["overconfidence"]) < 0.10 and row["bits_recovered"] < 0.30
            for row in fine
        )
        if correctly_uncertain:
            return ("fine stages are correctly uncertain, not blurry — cooling them would "
                    "make the robot worse, not better")

        hedging = [row for row in fine if row["overconfidence"] < -0.10]
        if hedging and min(temperatures) < 0.95:
            return ("fine stages hedge wider than their accuracy warrants — a cooler "
                    "schedule there is worth measuring")
        return "no clean reading; look at the table"
