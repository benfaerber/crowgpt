"""0114 — CrowGPT told the scene: bits about context in the call stream, by held-out likelihood.

    crowgpt/.venv/bin/python experiments/0114-how-much-do-the-calls-say-about-the-scene/run.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import joblib
import librosa
import numpy as np
import torch
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXP112 = REPO / "experiments" / "0112-does-crowgpt-hear-what-birdnet-misses"
sys.path.insert(0, str(EXP112))
import sets  # noqa: E402
from scoring import CONTEXTS, GroupedOvR  # noqa: E402

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.codec import CODEBOOK_SIZE, HOP, SAMPLE_RATE, Codec  # noqa: E402
from crowgpt.dualar import DualARConfig, DualARCrowGPT  # noqa: E402
from crowgpt.progress import Run  # noqa: E402
from crowgpt.tokens import Vocabulary  # noqa: E402

BASE = REPO / "crowgpt" / "results" / "quality-0101" / "dualar-quality-240k" / "step-240000.pt"
CACHE = sets.DATA_DIR / "experiments" / "0114-context-bits"
COUNT_HEAD = sets.DATA_DIR / "experiments" / "0109-crow-count" / "count_head.joblib"
CHANNELS = (*CONTEXTS, "none")
CHUNK_S, LEAD_S, MAX_CHUNKS = 6.0, 0.25, 24
STEPS, BATCH, LR, WARMUP, FLOOR, DECAY, DROPOUT = 2000, 8, 1e-4, 100, 0.1, 0.1, 0.2
SCORE_BATCH = 32


class Chunks:
    """6 s spans of two adjacent clean windows per archive recording, tokenised once."""

    def __init__(self, run: Run):
        self.recordings = [r for r in sets.ArchiveSet().recordings if sets.WindowTable.exists(r.key)]
        cache = CACHE / "chunks.npz"
        if cache.exists():
            saved = np.load(cache, allow_pickle=False)
            self.keys, self.codes, self.seconds = saved["keys"].tolist(), saved["codes"], saved["seconds"]
            self.lengths = saved["lengths"]
            with run.stage("tokenise") as stage:
                stage.update(1, 1, extra="cached")
        else:
            self._tokenise(run)
            CACHE.mkdir(parents=True, exist_ok=True)
            np.savez(cache, keys=np.array(self.keys), codes=self.codes, seconds=self.seconds, lengths=self.lengths)
        self.recording_of = {r.key: r for r in self.recordings}

    @staticmethod
    def spans(table: sets.WindowTable) -> list[tuple[float, float]]:
        clean = table.clean()
        starts = table.start
        pairs, i = [], 0
        while i < len(starts) - 1:
            if clean[i] and clean[i + 1] and abs(starts[i + 1] - starts[i] - sets.WINDOW_S) < 0.01:
                pairs.append((float(starts[i]), float(starts[i]) + CHUNK_S))
                i += 2
            else:
                i += 1
        if not pairs:
            best = int(np.argmax(np.where(clean, table.corvid, -1.0)))
            return [(float(starts[best]), float(starts[best]) + sets.WINDOW_S)]
        if len(pairs) > MAX_CHUNKS:
            pairs = [pairs[int(j)] for j in np.linspace(0, len(pairs) - 1, MAX_CHUNKS).round().astype(int)]
        return pairs

    def _tokenise(self, run: Run):
        codec = Codec(bandwidth=6.0, device="cuda")
        frames_max = int(math.ceil((CHUNK_S + LEAD_S) * SAMPLE_RATE / HOP))
        keys, codes, seconds, lengths = [], [], [], []
        with run.stage("tokenise") as stage:
            for n, r in enumerate(self.recordings, 1):
                samples, _ = librosa.load(str(r.path), sr=SAMPLE_RATE, mono=True)
                for start, end in self.spans(sets.WindowTable(r.key)):
                    lead = int(LEAD_S * SAMPLE_RATE)
                    lo, hi = int(start * SAMPLE_RATE), int(end * SAMPLE_RATE)
                    body = samples[lo:hi]
                    if body.size < SAMPLE_RATE:
                        continue
                    before = samples[max(0, lo - lead):lo]
                    before = np.concatenate([np.zeros(lead - len(before), dtype=np.float32), before])
                    peak = float(np.max(np.abs(body)))
                    wave = np.concatenate([before, body]) * (0.89 / peak if peak > 0 else 1.0)
                    c = codec.encode(wave.astype(np.float32)[None]).numpy()[0]
                    padded = np.zeros((c.shape[0], frames_max), dtype=np.int16)
                    padded[:, :c.shape[1]] = c[:, :frames_max]
                    keys.append(r.key)
                    codes.append(padded)
                    seconds.append(body.size / SAMPLE_RATE)
                    lengths.append(min(c.shape[1], frames_max))
                if n % 10 == 0 or n == len(self.recordings):
                    stage.update(n, len(self.recordings), extra=f"{len(keys)} chunks")
        self.keys, self.codes = keys, np.stack(codes)
        self.seconds, self.lengths = np.array(seconds, dtype=np.float32), np.array(lengths)


class ContextModel:
    """The 0101 base with its six channel tokens read as five contexts and `none`."""

    def __init__(self, device: str = "cuda"):
        blob = torch.load(BASE, map_location=device, weights_only=False)
        manifest = blob["manifest"]
        self.config = DualARConfig(**{k: v for k, v in blob["config"].items() if k != "arch"})
        self.state = blob["model"]
        self.vocabulary = Vocabulary(manifest["n_codebooks"], manifest["species"], (), CHANNELS,
                                     n_unit_buckets=manifest["n_unit_buckets"])
        self.device = device
        self.species = self.vocabulary.species_token("american-crow")
        self.model = self.fresh()
        self.unit = self._unit_argmax()

    def fresh(self) -> DualARCrowGPT:
        model = DualARCrowGPT(self.config).to(self.device)
        model.load_state_dict(self.state)
        return model

    @torch.no_grad()
    def _unit_argmax(self) -> int:
        start, end = self.vocabulary.prefix_slots()[2]
        prefix = torch.tensor([[self.species, self.vocabulary.channel_token("none")]], device=self.device)
        h = self.model.eval().temporal_hidden(self.model.token_embedding(prefix))
        return start + int((h[0, -1] @ self.model.head.weight[start:end].T).argmax())

    def sequences(self, chunks: Chunks, rows: np.ndarray, channels: list[str]) -> tuple[torch.Tensor, torch.Tensor]:
        """Inputs and targets, prefix and EOS never targets, padding never a target."""
        k = self.config.n_codebooks
        offsets = (np.arange(k) * CODEBOOK_SIZE)[:, None]
        longest = int(chunks.lengths[rows].max())
        p = self.vocabulary.prefix_len
        width = p + longest * k + 1
        inputs = np.zeros((len(rows), width), dtype=np.int64)
        targets = np.full((len(rows), width), -1, dtype=np.int64)
        for i, (row, channel) in enumerate(zip(rows, channels)):
            n = int(chunks.lengths[row])
            flat = (chunks.codes[row][:, :n].astype(np.int64) + offsets).T.reshape(-1)
            prefix = [self.species, self.vocabulary.channel_token(channel), self.unit,
                      self.vocabulary.duration_token(float(chunks.seconds[row]))]
            seq = np.concatenate([prefix, flat, [self.vocabulary.eos]])
            inputs[i, :len(seq)] = seq
            targets[i, p - 1:p - 1 + len(flat)] = flat
        return (torch.tensor(inputs[:, :-1], device=self.device), torch.tensor(targets[:, :-1], device=self.device))


class RowScorer:
    """Per-sequence frame NLL from the model's own pieces, split into stage 0 and stages 1-7."""

    def __init__(self, model: DualARCrowGPT, vocabulary: Vocabulary):
        self.model, self.vocabulary = model, vocabulary

    @torch.no_grad()
    def __call__(self, inputs: torch.Tensor, targets: torch.Tensor) -> tuple[np.ndarray, np.ndarray]:
        m = self.model
        prefix_in, frame_in, _, frame_tgt = m._unpack_batch(inputs, targets)
        h = m.temporal_hidden(torch.cat([m.token_embedding(prefix_in), m.embed_frames(frame_in)], dim=1))
        h_frames = h[:, m.prefix_len - 1:]
        active = (frame_tgt >= 0).any(dim=-1)
        rows = active.nonzero()[:, 0]
        ft = frame_tgt[active]
        prev = m.token_embedding(ft[:, :-1].clamp(min=0))
        dh = m.depth_hidden(torch.cat([h_frames[active].unsqueeze(1), prev], dim=1))
        coarse = torch.zeros(inputs.size(0), device=inputs.device)
        fine = torch.zeros(inputs.size(0), device=inputs.device)
        logits0 = dh[:, 0] @ m.head.weight[m.stage0_ids].T
        l0 = F.cross_entropy(logits0.float(), ft[:, 0].clamp(min=0), reduction="none") * (ft[:, 0] >= 0)
        coarse.index_add_(0, rows, l0)
        for s in range(1, m.n_codebooks):
            lo, hi = s * CODEBOOK_SIZE, (s + 1) * CODEBOOK_SIZE
            local = (ft[:, s] - lo).clamp(min=0)
            ls = F.cross_entropy((dh[:, s] @ m.head.weight[lo:hi].T).float(), local, reduction="none") * (ft[:, s] >= 0)
            fine.index_add_(0, rows, ls)
        return coarse.cpu().numpy(), fine.cpu().numpy()


class Fold:
    """Fine-tune on the training recordings, score every held-out chunk under every channel."""

    def __init__(self, cm: ContextModel, chunks: Chunks, train_keys: set, test_keys: set, labels: dict, seed: int):
        self.cm, self.chunks, self.labels, self.seed = cm, chunks, labels, seed
        keys = np.array(chunks.keys)
        self.train_rows = np.flatnonzero(np.isin(keys, list(train_keys)))
        self.test_rows = np.flatnonzero(np.isin(keys, list(test_keys)))

    def _lr(self, step: int) -> float:
        if step < WARMUP:
            return LR * (step + 1) / WARMUP
        progress = (step - WARMUP) / max(1, STEPS - WARMUP)
        return LR * (FLOOR + (1 - FLOOR) * 0.5 * (1 + math.cos(math.pi * progress)))

    def train(self, on_step) -> DualARCrowGPT:
        torch.manual_seed(self.seed)
        rng = np.random.default_rng(self.seed)
        model = self.cm.fresh().train()
        optimiser = model.optimiser(LR, weight_decay=DECAY)
        for step in range(STEPS):
            rows = rng.choice(self.train_rows, BATCH, replace=False)
            channels = [("none" if rng.random() < DROPOUT else self.labels[self.chunks.keys[r]]) for r in rows]
            inputs, targets = self.cm.sequences(self.chunks, rows, channels)
            for group in optimiser.param_groups:
                group["lr"] = self._lr(step)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model.loss(inputs, targets, self.cm.vocabulary)
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            if step % 100 == 0:
                on_step(step, float(loss))
        return model.eval()

    def score(self, model: DualARCrowGPT) -> dict[str, np.ndarray]:
        scorer = RowScorer(model, self.cm.vocabulary)
        out = {}
        for channel in CHANNELS:
            coarse, fine = np.zeros(len(self.test_rows)), np.zeros(len(self.test_rows))
            for i in range(0, len(self.test_rows), SCORE_BATCH):
                rows = self.test_rows[i:i + SCORE_BATCH]
                inputs, targets = self.cm.sequences(self.chunks, rows, [channel] * len(rows))
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    c, f = scorer(inputs, targets)
                coarse[i:i + len(rows)], fine[i:i + len(rows)] = c, f
            out[channel] = np.stack([coarse, fine], axis=1)
        return out


class Experiment:
    def __init__(self, run: Run):
        self.run = run
        self.chunks = Chunks(run)
        self.cm = ContextModel()
        keys = sorted(set(self.chunks.keys))
        recs = self.chunks.recording_of
        self.keys = keys
        self.labels = {k: recs[k].label for k in keys}
        self.groups = np.array([recs[k].group for k in keys])
        self.ovr = GroupedOvR(np.array([self.labels[k] for k in keys]), self.groups)

    def nll(self, arm: str, stage) -> dict:
        """Held-out [chunk, channel, (coarse, fine)] NLL in nats, for the true or shuffled arm."""
        cache = CACHE / f"nll_{arm}.npz"
        if cache.exists():
            return dict(np.load(cache))
        n = len(self.chunks.keys)
        nll = np.full((n, len(CHANNELS), 2), np.nan)
        for f, (train, test) in enumerate(self.ovr.folds):
            train_keys = {self.keys[i] for i in train}
            labels = dict(self.labels)
            if arm == "shuffled":
                ordered = sorted(train_keys)
                permuted = np.random.default_rng(1).permutation([labels[k] for k in ordered])
                labels.update(dict(zip(ordered, permuted)))
            fold = Fold(self.cm, self.chunks, train_keys, {self.keys[i] for i in test}, labels, seed=f)
            model = fold.train(lambda s, loss: stage.update(f * STEPS + s, 5 * STEPS, extra=f"{arm} fold {f} loss {loss:.3f}"))
            scored = fold.score(model)
            for c, channel in enumerate(CHANNELS):
                nll[fold.test_rows, c] = scored[channel]
            del model
            torch.cuda.empty_cache()
        np.savez(cache, nll=nll)
        return {"nll": nll}

    def analyse(self, nll: np.ndarray) -> dict:
        keys = np.array(self.chunks.keys)
        total = nll.sum(axis=2)
        ll = {k: -total[keys == k].sum(axis=0) for k in self.keys}
        scores = np.array([[ll[k][c] - ll[k][-1] for c in range(len(CONTEXTS))] for k in self.keys])
        true_index = np.array([CHANNELS.index(self.labels[k]) for k in keys])
        rows = np.arange(len(keys))
        bits = (total[rows, -1] - total[rows, true_index]) / math.log(2)
        coarse = (nll[rows, -1, 0] - nll[rows, true_index, 0]) / math.log(2)
        fine = (nll[rows, -1, 1] - nll[rows, true_index, 1]) / math.log(2)
        return {"scores": scores, "bits": bits, "coarse_bits": coarse, "fine_bits": fine}

    def per_recording(self, chunk_values: np.ndarray) -> np.ndarray:
        keys = np.array(self.chunks.keys)
        return np.array([chunk_values[keys == k].mean() for k in self.keys])

    def bits_difference(self, a: np.ndarray, b: np.ndarray) -> dict:
        ra, rb = self.per_recording(a), self.per_recording(b)
        diffs = [float(ra[r].mean() - rb[r].mean()) for r in self.ovr.resamples()]
        return {"true_bits_per_chunk": round(float(a.mean()), 4), "shuffled_bits_per_chunk": round(float(b.mean()), 4),
                "difference_recording_mean": round(float(ra.mean() - rb.mean()), 4),
                "ci95": [round(float(np.percentile(diffs, 2.5)), 4), round(float(np.percentile(diffs, 97.5)), 4)]}

    def crowd_removed(self, scores: np.ndarray) -> dict:
        head = joblib.load(COUNT_HEAD)
        count = []
        for k in self.keys:
            table = sets.WindowTable(k)
            crow = table.corvid >= 0.25
            count.append(float(head.decision_function(table.embedding[crow].mean(0, keepdims=True))[0]) if crow.any() else 0.0)
        count = np.array(count)
        residual = np.zeros_like(scores)
        for c in range(scores.shape[1]):
            slope, intercept = np.polyfit(count, scores[:, c], 1)
            residual[:, c] = scores[:, c] - (slope * count + intercept)
        return self.ovr.report(residual)

    def main(self) -> dict:
        with self.run.stage("finetune_true") as stage:
            true = self.analyse(self.nll("true", stage)["nll"])
        with self.run.stage("finetune_shuffled") as stage:
            shuffled = self.analyse(self.nll("shuffled", stage)["nll"])
        with self.run.stage("analyse") as stage:
            labels = np.array([self.labels[k] for k in self.keys])
            primary = self.ovr.report(true["scores"])
            control = self.ovr.report(shuffled["scores"])
            bits = self.bits_difference(true["bits"], shuffled["bits"])
            keys = np.array(self.chunks.keys)
            chunk_labels = np.array([self.labels[k] for k in keys])
            report = {
                "recordings": len(self.keys), "chunks": len(keys), "recordists": len(set(self.groups)),
                "per_context_recordings": {c: int((labels == c).sum()) for c in CONTEXTS},
                "PRIMARY_true_label_macro_auc": primary,
                "shuffled_control_macro_auc": control,
                "auc_margin_over_control": round(primary["macro_auc"] - control["macro_auc"], 4),
                "bits": bits,
                "S1_per_context_bits": {c: {"true": round(float(true["bits"][chunk_labels == c].mean()), 4),
                                            "shuffled": round(float(shuffled["bits"][chunk_labels == c].mean()), 4)}
                                        for c in CONTEXTS},
                "S2_crowd_removed": self.crowd_removed(true["scores"]),
                "S3_bits_by_stage": {"true_coarse": round(float(true["coarse_bits"].mean()), 4),
                                     "true_fine": round(float(true["fine_bits"].mean()), 4),
                                     "shuffled_coarse": round(float(shuffled["coarse_bits"].mean()), 4),
                                     "shuffled_fine": round(float(shuffled["fine_bits"].mean()), 4)},
            }
            passes = (primary["macro_auc"] >= 0.70 and report["auc_margin_over_control"] >= 0.05
                      and bits["ci95"][0] > 0)
            report["reading"] = "passes" if passes else "null"
            stage.update(1, 1)
        return report


def main():
    run = Run("0114 context-conditioned CrowGPT", ["tokenise", "finetune_true", "finetune_shuffled", "analyse"])
    report = Experiment(run).main()
    s4 = EXP112 / "results.json"
    if s4.exists():
        archive = json.loads(s4.read_text()).get("S2_archive_contexts", {})
        report["S4_beside_discriminative"] = {n: archive.get(n, {}).get("macro_auc") for n in ("birdnet", "crowgpt_b4")}
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    run.note(f"macro AUC {report['PRIMARY_true_label_macro_auc']['macro_auc']}, reading {report['reading']}")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
