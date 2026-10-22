"""Compare models on identical conditions, with error bars.

The judge this replaces scored one model 50.0% and then 31.7%. Both were honest
readings of independent samples; the instrument simply could not resolve what it
was being asked. Everything here exists to fix that.

MATCHED CONDITIONS. Every model is scored on the same list of (species, seed,
ambience clip). Most of the variance in a judged score is the condition, not the
model, so comparing like with like cancels it — this is what buys resolution,
far more than sample count does.

TWO EMBEDDING SPACES. Fréchet distance against the real held-out set, computed
in BirdNET's space (is it a corvid) and AST's (does it sound like a recording).
0014 showed BirdNET is close to blind to quality, so a number from it alone
cannot tell a better crow from a cleaner one.

AND THE OLD METRIC, with intervals. Detection rate is kept because it is what
every previous result was quoted in, and dropping it would make this run
incomparable with the last three.
"""

import numpy as np

from crowgpt.codec import normalise
from crowgpt.metrics import bootstrap_ci, frechet_distance, paired_difference


class Conditions:
    """The fixed list every model is scored against."""

    def __init__(self, species, per_species=12, seed=0):
        rng = np.random.default_rng(seed)
        self.items = [
            {"species": slug, "seed": int(rng.integers(2**31)), "ambience": int(rng.integers(1000))}
            for slug in species
            for _ in range(per_species)
        ]

    def __len__(self):
        return len(self.items)


class Evaluation:
    """Scores a set of models, plus the real and codec reference arms."""

    def __init__(self, bout_root, token_dir, ambience, judge, embedders, conditions):
        from crowgpt.tokens import BoutStore, TokenDataset

        self.store = BoutStore(bout_root)
        self.test = TokenDataset(token_dir, "test")
        self.ambience = ambience
        self.judge = judge
        self.embedders = embedders
        self.conditions = conditions

    def _place(self, clip, condition):
        """Same ambience for the same condition, whichever model produced it."""
        self.ambience.rng = np.random.default_rng(condition["ambience"])
        return self.ambience.place(clip)

    def real_arm(self):
        held = {row["group_key"] for row in self.test.records}
        by_species = {}
        for row in self.store.index:
            if row["group_key"] in held:
                by_species.setdefault(row["species"], []).append(row)
        clips = []
        for condition in self.conditions.items:
            pool = by_species.get(condition["species"]) or []
            if not pool:
                clips.append(None)
                continue
            row = pool[condition["seed"] % len(pool)]
            clips.append(self._place(normalise(self.store.audio(row)), condition))
        return clips

    def codec_arm(self, codec, real_clips):
        return [None if c is None else self._place(codec.roundtrip(c)[0][: c.size], cond)
                for c, cond in zip(real_clips, self.conditions.items)]

    def model_arm(self, sampler, on_progress=None):
        clips = []
        for i, condition in enumerate(self.conditions.items):
            audio = sampler.audio(condition["species"], seed=condition["seed"])
            clips.append(self._place(audio, condition) if audio.size else None)
            if on_progress and (i + 1) % 12 == 0:
                on_progress(i + 1, len(self.conditions))
        return clips

    def score(self, clips):
        """BirdNET confidence per clip, None where generation produced nothing.

        One subprocess call for the whole arm — each one pays interpreter and
        model startup, so scoring clip by clip would spend most of the run in
        BirdNET's constructor.
        """
        present = [(i, c) for i, c in enumerate(clips) if c is not None]
        out = [None] * len(clips)
        if not present:
            return out
        values = self.judge.confidences([c for _, c in present])
        for (i, _), value in zip(present, values):
            out[i] = value
        return out

    def summarise(self, name, confidences, clips, reference_embeddings=None):
        usable = np.array([c for c in confidences if c is not None])
        out = {"arm": name, "n": int(usable.size)}
        if usable.size:
            low, high = bootstrap_ci(usable)
            out["mean_conf"] = round(float(usable.mean()), 4)
            out["mean_conf_ci"] = [round(low, 4), round(high, 4)]
            detected = (usable >= self.judge.crow_min).astype(float)
            low, high = bootstrap_ci(detected)
            out["detected_rate"] = round(float(detected.mean()), 4)
            out["detected_ci"] = [round(low, 4), round(high, 4)]
        if reference_embeddings is not None:
            out["fad"] = {}
            for embedder in self.embedders:
                theirs = embedder.embed([c for c in clips if c is not None], 24000)
                mine = reference_embeddings[embedder.name]
                if len(theirs) >= 2 and len(mine) >= 2:
                    out["fad"][embedder.name] = round(frechet_distance(mine, theirs), 3)
        return out

    def embed_reference(self, clips):
        usable = [c for c in clips if c is not None]
        return {e.name: e.embed(usable, 24000) for e in self.embedders}


def compare(results, key="mean_conf_values"):
    """Paired differences between every model and the best one."""
    models = {n: v for n, v in results.items() if key in v}
    if len(models) < 2:
        return {}
    best = max(models, key=lambda n: np.mean(models[n][key]))
    out = {"best": best, "against": {}}
    for name, value in models.items():
        if name == best:
            continue
        paired = [(a, b) for a, b in zip(models[best][key], value[key])
                  if a is not None and b is not None]
        if len(paired) < 5:
            continue
        a, b = zip(*paired)
        out["against"][name] = paired_difference(np.array(a), np.array(b))
    return out
