"""crowgpt <stage> — the pipeline, one stage at a time.

Stages are deliberately separate commands rather than one run: extraction takes
half an hour and the gate can tell you to stop entirely, so neither should be
something you re-run to get to the next thing.
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crowgpt.gpu import claim  # noqa: E402

claim()  # must precede any birdnetlib import; see crowgpt/gpu.py
HERE = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "crowgpt"
BOUTS = DATA / "bouts"
TOKENS = DATA / "tokens"
RESULTS = HERE / "results"
EXPERIMENT = REPO / "experiments" / "0014-can-a-neural-codec-carry-a-caw"


def _report(payload):
    print(json.dumps(payload, indent=2))


def extract(args):
    from crowgpt.extract import Extractor
    from crowgpt.progress import Run

    # Extraction used to print without ever writing a progress record,
    # so a multi-hour rebuild was invisible to the dashboard — the exact gap
    # CLAUDE.md's rule exists to close. Extractor already accepts an
    # `on_progress(line, done, total)` hook; this drives a Run with it, which
    # writes both files from one state.
    run = Run("CROWGPT — EXTRACT", ["extract"])
    with run.stage("extract") as stage:
        def on_progress(line, done, total):
            if done is not None and total:
                stage.update(done, total, extra=line[:60])
            else:
                stage.say(line[:80])

        summary = Extractor(Path(args.out) if args.out else BOUTS,
                            limit_per_species=args.limit,
                            workers=args.workers, on_progress=on_progress).run()
        run.note(f"{summary.get('bouts', '?')} bouts from "
                 f"{summary.get('recordings', '?')} recordings")
    _report(summary)


def gate(args):
    from crowgpt.gate import Gate

    results = Gate(per_species=args.per_species).run()
    EXPERIMENT.mkdir(parents=True, exist_ok=True)
    (EXPERIMENT / "results.json").write_text(json.dumps(results, indent=2))
    _report({k: v for k, v in results.items() if k != "arms"})
    print(f"\nwrote {EXPERIMENT / 'results.json'}")


def label_calltypes(args):
    """Pseudo-label a bout store with call types — the 0021 recipe, committed.

    This step built model-calltype and was never checked in: the head, the
    labels and the split discipline all existed in calltype.py, but the driver
    that ran them over a corpus was ad hoc, and its output (bouts-v1's
    call_types.json) is positional — keyed to one index — so it died with its
    bout store. This writes the file beside the store it belongs to, with the
    store's size baked in so a mismatched pairing fails loudly at tokenize.

    The split discipline from calltype.py holds: the head fits only on human
    labels whose recording is in the TRAIN split (same seed as tokenize), so
    held-out human labels stay unseen by everything and 0021-style judging
    stays honest. Train-split human labels overwrite their own bouts'
    pseudo-labels — truth beats a guess where truth exists (0022's merge).
    """
    from collections import Counter

    import numpy as np

    from crowgpt.birdnet import BirdNet
    from crowgpt.calltype import (CORE, MIN_PER_CLASS, BoutCallTypes,
                                  check_vocabulary, human_labels, label_bouts)
    from crowgpt.codec import normalise
    from crowgpt.progress import Run
    from crowgpt.tokens import BoutStore

    check_vocabulary()
    bouts_dir = Path(args.bouts) if args.bouts else BOUTS
    store = BoutStore(bouts_dir)
    splits = store.split(seed=args.seed)
    where = {i: name for name, indices in splits.items() for i in indices}
    tagged = label_bouts(store.index, human_labels(), species=args.species)
    train_tagged = {i: t for i, t in tagged.items() if where[i] == "train"}
    counts = Counter(train_tagged.values())
    thin = [c for c in CORE if counts[c] < MIN_PER_CLASS]
    if thin:
        raise SystemExit(
            f"train-split human labels too thin for {thin} ({dict(counts)}) — "
            "fitting without a class would shrink the prefix vocabulary and "
            "silently re-point token ids")

    targets = [i for i, row in enumerate(store.index)
               if row["species"] == args.species]
    birdnet = BirdNet(sample_rate=24000)

    def embed(positions, stage, done_offset, total):
        vectors, kept = [], []
        for start in range(0, len(positions), 400):
            chunk = positions[start:start + 400]
            got, index = birdnet.embed_indexed(
                [normalise(store.audio(store.index[p])) for p in chunk])
            if len(got):
                vectors.append(got)
                kept.extend(chunk[j] for j in index)
            stage.update(done_offset + min(start + 400, len(positions)), total,
                         extra=f"kept {len(kept)}")
        return (np.concatenate(vectors) if vectors else np.zeros((0, 1024))), kept

    run = Run(f"LABEL {bouts_dir.name} call types", ["fit head", "label corpus"])
    total = len(train_tagged) + len(targets)
    with run.stage("fit head") as stage:
        train_x, train_pos = embed(sorted(train_tagged), stage, 0, total)
        head = BoutCallTypes()
        fitted = head.fit(train_x, [train_tagged[p] for p in train_pos])
        stage.say(f"head trained on {fitted['trained_on']}: {fitted['classes']}")

    call_types = {}
    with run.stage("label corpus") as stage:
        for start in range(0, len(targets), 400):
            chunk = targets[start:start + 400]
            got, index = birdnet.embed_indexed(
                [normalise(store.audio(store.index[p])) for p in chunk])
            if len(got):
                for position, label in zip((chunk[j] for j in index),
                                           head.predict(got)):
                    call_types[position] = label
            stage.update(len(train_tagged) + min(start + 400, len(targets)),
                         total, extra=f"labelled {len(call_types)}")
        call_types.update(train_tagged)
        histogram = Counter(call_types.values())
        run.note(" · ".join(f"{k} {v}" for k, v in histogram.most_common()))

    payload = {
        "bouts": bouts_dir.name,
        "n_bouts": len(store),
        "species": args.species,
        "seed": args.seed,
        "head": fitted,
        "min_confidence": head.min_confidence,
        "histogram": dict(histogram),
        "held_out_human": {str(i): t for i, t in tagged.items()
                           if where[i] != "train"},
        "call_types": {str(i): t for i, t in call_types.items()},
    }
    out = Path(args.out) if args.out else bouts_dir / "call_types.json"
    out.write_text(json.dumps(payload))
    _report({"out": str(out), "n_bouts": payload["n_bouts"],
             "head": fitted, "histogram": payload["histogram"]})


def tokenize(args):
    from crowgpt.tokens import BoutStore, TokenWriter

    store = BoutStore(Path(args.bouts) if args.bouts else BOUTS)
    splits = store.split(seed=args.seed)
    from crowgpt.calltype_labels import load_calltypes

    call_types = load_calltypes(args.call_types, store) if args.call_types else None
    out = Path(args.out) if args.out else TOKENS
    codec = None
    if args.codec != "encodec":
        from crowgpt.dac_codec import DacCodec

        if not args.keep:
            raise SystemExit("--codec dac needs --keep to say how many codebooks")
        codec = DacCodec(n_codebooks=args.keep, model_type=args.codec.split("dac-", 1)[1])
    from crowgpt.progress import Run

    print(f"   {len(store)} bouts · " + " · ".join(f"{k} {len(v)}" for k, v in splits.items()))
    print(f"   -> {out}")

    # One bar across all three splits, not three that restart at zero — a
    # fraction that resets twice reads as a stall. Same reason the experiments
    # thread on_progress through; the CLI path was the one that never did.
    offsets, running = {}, 0
    for name in splits:
        offsets[name] = running
        running += len(splits[name])

    run = Run("CROWGPT — TOKENIZE", ["tokenize"])
    with run.stage("tokenize") as stage:
        stage.say(f"{len(store)} bouts -> {out}")
        manifest = TokenWriter(store, out, bandwidth=args.bandwidth, keep=args.keep,
                               codec=codec, augment=not args.no_augment,
                               variants=args.variants, unit_buckets=args.units,
                               call_types=call_types).run(
            splits, on_progress=lambda split, done, _n: stage.update(
                offsets[split] + done, running, extra=split))
        run.note(f"K={manifest['n_codebooks']} vocab {manifest['vocab_size']} "
                 f"({len(manifest['species'])} species)")
    _report(manifest)


def latents(args):
    """Bouts -> continuous DAC latent memmaps, the target 0052 opened up.

    AMERICAN CROW ONLY BY DEFAULT, and that is an evidenced choice rather than a
    shortcut. 0049 compared a 46-species model against an American-Crow-only one
    on the same held-out American Crow bouts and found it neutral — P(multi
    preferred) 0.42, CI [0.28, 0.57], catch 10/10 — so the other 45 species buy
    nothing for the only species anyone judges. It is also 70.6% of the corpus,
    so this halves both the disk and the encode for no measured loss.
    """
    from crowgpt.continuous import ContinuousCodec, LatentWriter
    from crowgpt.progress import Run
    from crowgpt.tokens import BoutStore

    store = BoutStore(BOUTS)
    splits = store.split(seed=args.seed)
    out = Path(args.out) if args.out else DATA / "latents"
    species = None if args.all_species else [args.species]

    codec = ContinuousCodec(n_stages=args.stages)
    kept = [r for r in store.index if species is None or r["species"] in species]
    print(f"   {len(kept)} bouts · {codec.dim} dims · {codec.n_stages} stages")
    print(f"   -> {out}")

    run = Run("CROWGPT — LATENTS", ["encode"])
    with run.stage("encode") as stage:
        stage.say(f"{len(kept)} bouts -> {out}")
        writer = LatentWriter(store, out, codec, species=species)
        manifest = writer.run(
            splits, batch_size=args.batch_size,
            on_progress=lambda _split, done, total: stage.update(done, total))
        frames = sum(s["frames"] for s in manifest["splits"].values())
        run.note(f"{frames} frames · {frames * codec.dim * 2 / 1e9:.2f} GB")
    _report(manifest)


def train(args):
    from crowgpt.train import Trainer

    token_dir = Path(args.token_dir) if args.token_dir else TOKENS
    out_dir = Path(args.out) if args.out else RESULTS / "model"
    buckets = None
    if args.channels:
        from crowgpt.channel import ChannelBuckets

        buckets = ChannelBuckets.load(args.channels)
        print(f"   channel-conditioned: {len(set(buckets.mapping.values()))} buckets")
    print(f"   {token_dir} -> {out_dir}")
    # A TRAINING RUN LAUNCHED FROM THE CLI USED TO REPORT NOWHERE BUT STDOUT.
    # `overnight.py` wraps its runs in a Run and this path did not, so a job an
    # agent starts and walks away from is invisible on the dashboard for hours —
    # the exact failure the progress record exists to prevent. on_step fires every 25
    # steps, comfortably inside the 600 s stale window; on_eval alone would not
    # be, at roughly nine minutes between writes.
    from crowgpt.progress import Run

    run = Run(f"TRAIN {out_dir.name}", ["train"])
    trainer = Trainer(
        token_dir,
        out_dir,
        steps=args.steps,
        batch_size=args.batch_size,
        dropout=args.dropout,
        n_embd=args.n_embd,
        n_layer=args.n_layer,
        memory_budget=args.memory_budget,
        accumulate=args.accumulate,
        block_size=args.block_size,
        loss_from_stage=args.loss_from_stage,
        channels=buckets,
    )
    with run.stage("train") as stage:
        stage.update(0, args.steps)
        history = trainer.run(
            on_step=lambda step, total: stage.update(step, total),
            on_eval=lambda step, val: run.note(f"step {step}: val {val:.4f}"),
        )
        stage.say(f"best val {history['best_val']:.4f}")
    _report({"best_val": history["best_val"]})


def flow_train(args):
    """Train the rectified-flow DiT on continuous latents (0052's route)."""
    from crowgpt.flow import Config
    from crowgpt.flow_train import FlowTrainer
    from crowgpt.progress import Run

    latent_dir = Path(args.latent_dir) if args.latent_dir else DATA / "latents"
    out_dir = Path(args.out) if args.out else RESULTS / "model-flow"
    print(f"   {latent_dir} -> {out_dir}")

    run = Run(f"FLOW {out_dir.name}", ["train"])
    trainer = FlowTrainer(
        latent_dir, out_dir, steps=args.steps, batch_size=args.batch_size,
        learning_rate=args.lr, eval_every=args.eval_every,
        normalisation=args.normalisation, t_sampling=args.t_sampling,
        t_mean=args.t_mean,
        config=Config(dim=256, n_layer=args.n_layer, n_head=args.n_head,
                      n_embd=args.n_embd, dropout=args.dropout,
                      max_frames=args.max_frames) if args.n_embd else None,
    )
    print(f"   {trainer.model.n_params()/1e6:.1f}M parameters · "
          f"{trainer.max_frames} frames max · dim {trainer.config.dim}")
    with run.stage("train") as stage:
        stage.update(0, args.steps)
        history = trainer.run(
            on_step=lambda step, total: stage.update(step, total),
            on_eval=lambda step, val: run.note(f"step {step}: val {val:.4f}"),
        )
        stage.say(f"best val {history['best_val']:.4f}")
    _report({"best_val": history["best_val"]})


def flow_sample(args):
    from crowgpt.flow_sample import FlowSampler, write_clips

    latent_dir = Path(args.latent_dir) if args.latent_dir else DATA / "latents"
    model_dir = Path(args.model) if args.model else RESULTS / "model-flow"
    out_dir = Path(args.out) if args.out else RESULTS / "flow-clips"

    sampler = FlowSampler(model_dir, latent_dir)
    clips = sampler.generate(count=args.count, steps=args.steps, seed=args.seed)
    paths = write_clips(clips, out_dir)
    print(f"   {len(paths)} clips -> {out_dir}")
    _report({"clips": len(paths),
             "seconds": round(sum(len(c) for c in clips) / 24000, 1)})


def channels(args):
    """Build the channel buckets: one descriptor per recording, then k-means."""
    from crowgpt.channel import ChannelBuckets, describe_corpus
    from crowgpt.progress import Run

    out = Path(args.out) if args.out else DATA / "channels.json"
    run = Run("CHANNEL BUCKETS", ["describe", "cluster"])
    with run.stage("describe") as stage:
        stage.update(0, 1)
        described = describe_corpus(
            BOUTS, per_recording=args.per_recording,
            on_progress=lambda done, total: stage.update(done, total))
        stage.say(f"{len(described)} recordings described")
    with run.stage("cluster") as stage:
        buckets = ChannelBuckets().fit(described, n_buckets=args.buckets)
        buckets.save(out)
        stage.say(f"{len(set(buckets.mapping.values()))} buckets -> {out}")
    run.note(f"{len(buckets.mapping)} recordings in "
             f"{len(set(buckets.mapping.values()))} channel buckets")
    print(f"wrote {out}")


def sample(args):
    from crowgpt.sample import Sampler, write_samples

    sampler = Sampler(RESULTS / "model" / "model.pt", token_dir=TOKENS)
    written = write_samples(
        sampler, RESULTS / "samples", per_species=args.n, temperature=args.temperature
    )
    print(f"wrote {len(written)} samples to {RESULTS / 'samples'}")


def judge(args):
    from crowgpt.corpus import Corpus
    from crowgpt.judge import Judgement
    from crowgpt.sample import Sampler

    sampler = Sampler(RESULTS / "model" / "model.pt", token_dir=TOKENS)
    judgement = Judgement(sampler, TOKENS, BOUTS, per_species=args.per_species)
    ambience = [r for recs in Corpus().recordings().values() for r in recs[:6]]
    results, clips = judgement.run(ambience)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "judge.json").write_text(json.dumps(results, indent=2))
    _report(results)
    _stash_clips(clips)


def _stash_clips(clips):
    """Audio to npz, metadata to json — 24 three-second clips is 7M floats."""
    import numpy as np

    np.savez_compressed(
        RESULTS / "clips.npz", **{str(i): c["audio"] for i, c in enumerate(clips)}
    )
    (RESULTS / "clips.json").write_text(
        json.dumps([{k: v for k, v in c.items() if k != "audio"} for c in clips])
    )


def _balanced(clips, wanted):
    """Equal real and generated, spread across species.

    The judge emits its arms in blocks, so taking the first N gives N real
    clips and nothing to compare them against — which still renders a
    perfectly convincing page that measures nothing.
    """
    from collections import defaultdict

    buckets = defaultdict(list)
    for clip in clips:
        if clip["arm"] in ("A_real", "C_generated"):
            buckets[(clip["arm"], clip["species"])].append(clip)

    picked, arms = [], ("A_real", "C_generated")
    species = sorted({s for _, s in buckets})
    round_index = 0
    while len(picked) < wanted and any(buckets.values()):
        for arm in arms:
            slug = species[round_index % len(species)]
            if buckets[(arm, slug)] and len(picked) < wanted:
                picked.append(buckets[(arm, slug)].pop())
        round_index += 1
    return picked


def _power_note(n):
    """What an interval of this width can and cannot settle.

    Printed rather than assumed, because the whole point of recording the
    sitting is that "I could not tell" stops being a claim without a number
    behind it. Halfwidth is the normal approximation at p = 0.5, which is the
    only place it matters here.
    """
    import math

    if n < 2:
        return "no trials"
    halfwidth = 1.96 * math.sqrt(0.25 / n)
    verdict = "can settle whether chance is excluded" if halfwidth <= 0.10 else (
        "enough to show he can still tell, not enough to prove he cannot"
        if halfwidth <= 0.20 else "underpowered for any verdict"
    )
    return f"n={n} -> +/-{halfwidth:.3f} at chance; {verdict}"


def _generate_clips(model, focus, wanted, cache):
    """A focused real-vs-generated set on matched conditions.

    The judge's stash spreads its clips evenly over six species, so asking it
    for a sitting about one of them leaves a twelfth of what it collected —
    twenty-four trials, whose interval is too wide to settle anything. This
    generates against `evaluate.Conditions` instead, which means every clip
    carries a condition index and two checkpoints judged this way can be
    compared trial by trial rather than in aggregate.

    No BirdNET anywhere. Its confidence is decoration on the reveal line, and
    reaching it would drag a subprocess and a model load into a page build.
    """
    import numpy as np

    from crowgpt.corpus import Corpus
    from crowgpt.evaluate import Conditions, Evaluation
    from crowgpt.judge import Ambience
    from crowgpt.sample import Sampler

    sampler = Sampler(RESULTS / model / "model.pt", token_dir=TOKENS)
    species = [s for s in sampler.species if focus.keeps(s)]
    if not species:
        sys.exit(f"{model} was not trained on {focus.label()}")

    conditions = Conditions(species, per_species=max(1, wanted // (2 * len(species))))
    print(f"   {len(conditions)} conditions x 2 arms for {focus.label()}", flush=True)

    ambience = Ambience([r for recs in Corpus().recordings().values() for r in recs[:4]])
    evaluation = Evaluation(BOUTS, TOKENS, ambience, None, [], conditions)

    real = evaluation.real_arm()
    print("   generating", flush=True)
    made = evaluation.model_arm(sampler, on_progress=lambda i, n: print(f"   {i}/{n}", flush=True))

    clips, audio = [], {}
    for arm, samples in (("A_real", real), ("C_generated", made)):
        for index, sound in enumerate(samples):
            if sound is None or not len(sound):
                continue
            key = str(len(clips))
            audio[key] = np.asarray(sound, dtype=np.float32)
            clips.append({
                "arm": arm,
                "species": conditions.items[index]["species"],
                "condition_index": index,
                "clip_id": len(clips),
                "conf": None,
                "called": None,
            })

    np.savez_compressed(cache.with_suffix(".npz"), **audio)
    cache.write_text(json.dumps(clips))
    return clips, audio


def _clips_for(model, focus, wanted, generate):
    """One checkpoint's clips, with the weights that made them attached.

    Every clip carries its own checkpoint so an interleaved sheet can be pooled
    apart afterwards. The real arm is tagged too: a checkpoint's false-alarm
    rate is part of its own d-prime, so its reals have to travel with it exactly
    as they would in a sitting of its own.
    """
    import numpy as np

    from crowgpt.listen import Checkpoint

    slug = model.replace("/", "-")
    cache = RESULTS / f"clips-{slug}-{focus.slug()}.json"
    if generate or not cache.exists():
        clips, audio = _generate_clips(model, focus, wanted, cache)
    else:
        clips = json.loads(cache.read_text())
        audio = np.load(cache.with_suffix(".npz"))
    for clip in clips:
        clip["audio"] = audio[str(clip["clip_id"])]

    folder = RESULTS / model
    stamp = Checkpoint.load(folder).as_dict() if (folder / "model.pt").exists() else {"name": model}
    for clip in clips:
        clip["checkpoint"] = stamp
    return clips, stamp


def _interleaved(args, focus):
    """One sitting, two checkpoints, shuffled together.

    THE REASON THIS EXISTS. On 2026-08-01 the same weights scored 75.0% on a
    Friday evening and 83.3% on a Saturday morning — 8.3 points of listener
    between two sittings, which was larger than the model difference being
    measured, and very nearly went into the record as a quality regression.
    Comparing two checkpoints across two sittings measures the listener as much
    as the models. Interleaved, practice and alertness are shared and cancel,
    and the paired-by-condition test has both arms from one sitting.
    """
    half = max(2, args.n // 2)
    per_arm = max(1, half // 2)
    left, left_stamp = _clips_for(args.model, focus, half, args.generate)
    right, right_stamp = _clips_for(args.against, focus, half, args.generate)
    if left_stamp.get("fingerprint") and left_stamp["fingerprint"] == right_stamp.get("fingerprint"):
        sys.exit(f"{args.model} and {args.against} are the same weights — "
                 f"an interleaved sheet of one checkpoint measures nothing.")

    # REAL AUDIO IS NOT PRODUCED BY A CHECKPOINT, and both caches drew theirs
    # from the same conditions, so taking each cache's real arm puts every real
    # clip in the sitting TWICE. Caught by hashing the audio: 45 unique clips in
    # a 60-trial sheet. A listener hearing the same bout twice recognises it,
    # and the second answer is not an independent trial. One pool, split.
    reals = sorted([c for c in focus.filter(left) if c["arm"] == "A_real"],
                   key=lambda c: c.get("condition_index") or 0)
    mid = len(reals) // 2
    generated = {
        left_stamp.get("fingerprint"): [c for c in focus.filter(left) if c["arm"] == "C_generated"],
        right_stamp.get("fingerprint"): [c for c in focus.filter(right) if c["arm"] == "C_generated"],
    }

    keep = []
    for stamp, share in ((left_stamp, reals[:mid]), (right_stamp, reals[mid:])):
        for clip in share[:per_arm]:
            clip = dict(clip)
            clip["checkpoint"] = stamp
            keep.append(clip)
    for stamp in (left_stamp, right_stamp):
        for clip in generated[stamp.get("fingerprint")][:per_arm]:
            clip = dict(clip)
            clip["checkpoint"] = stamp
            keep.append(clip)

    for i, clip in enumerate(keep):
        clip["clip_id"] = i          # the two caches both number from zero
    return keep, {"name": f"{left_stamp.get('name')} vs {right_stamp.get('name')}",
                  "interleaved": [left_stamp, right_stamp], "focus": focus.slug()}


def demo(args):
    import numpy as np

    from crowgpt.demo import DemoPage
    from crowgpt.focus import Focus
    from crowgpt.listen import Checkpoint

    focus = Focus.parse(args.species)
    if getattr(args, "against", None):
        keep, checkpoint = _interleaved(args, focus)
        page = DemoPage(keep, {"Checkpoints": 2, "Trials": len(keep),
                               "Species": focus.label()},
                        checkpoint=checkpoint).write(
            RESULTS / f"demo-interleaved-{focus.slug()}.html")
        print(f"wrote {page}")
        print(f"   {len(keep)} trials across 2 checkpoints · {_power_note(len(keep) // 2)} per arm")
        print(f"   save the session into {RESULTS / 'listening' / 'interleaved'}/")
        return
    # A model name can be a PATH — the sweep arms live at
    # sweep-0023/batch-32-dropout-0 — so it cannot go into a filename raw. It
    # did, and the slash turned the cache into a directory that does not exist:
    # the page still wrote (DemoPage mkdirs its parent) while the npz beside it
    # failed, which is a broken sitting rather than a clean error.
    slug = args.model.replace("/", "-")
    cache = RESULTS / f"clips-{slug}-{focus.slug()}.json"

    if args.generate or (cache.exists() and not args.stash):
        if args.generate or not cache.exists():
            clips, audio = _generate_clips(args.model, focus, args.n, cache)
        else:
            clips = json.loads(cache.read_text())
            audio = np.load(cache.with_suffix(".npz"))
        for clip in clips:
            clip["audio"] = audio[str(clip["clip_id"])]
    elif not args.stash:
        # THE FALLBACK USED TO BE SILENT, AND IT CORRUPTED THE ONE HONEST
        # INSTRUMENT. results/clips.json is whatever model last ran `make
        # judge`. Asking for a checkpoint with no cache of its own landed here,
        # served that other model's audio, and still stamped THIS checkpoint's
        # hash on the session — so a sitting would pool into `make listen` as a
        # reading of weights it never heard. Sessions key on the hash precisely
        # so two models can never be averaged together, and this quietly did it.
        sys.exit(
            f"no clips cached for {args.model} ({focus.label()}).\n"
            f"  `make demo MODEL={args.model} GENERATE=1` to make a matched set "
            f"from those weights, which is almost certainly what you want.\n"
            f"  Add --stash only if you deliberately want the shared stash, "
            f"which was generated by whichever model last ran `make judge` and "
            f"is NOT this one."
        )
    else:
        clips = json.loads((RESULTS / "clips.json").read_text())
        audio = np.load(RESULTS / "clips.npz")
        for i, clip in enumerate(clips):
            clip["audio"] = audio[str(i)]
            clip["clip_id"] = i

    available = focus.filter(clips)
    if not available:
        sys.exit(f"no stashed clips for {focus.label()} — run `make judge` first")
    keep = _balanced(available, args.n)

    checkpoint = {}
    folder = RESULTS / args.model
    if (folder / "model.pt").exists():
        checkpoint = Checkpoint.load(folder).as_dict()
    else:
        print(f"   no {args.model}/model.pt — the sitting will not be poolable", flush=True)
    checkpoint["focus"] = focus.slug()

    facts = {}
    if (RESULTS / "judge.json").exists():
        judged = json.loads((RESULTS / "judge.json").read_text())
        facts["Real detected"] = f"{judged['A_real']['detected_rate']:.0%}"
        facts["Generated detected"] = f"{judged['C_generated']['detected_rate']:.0%}"
    if (BOUTS / "summary.json").exists():
        summary = json.loads((BOUTS / "summary.json").read_text())
        facts["Training bouts"] = f"{summary['kept']:,}"
        facts["Hours"] = f"{summary['hours']:.1f}"
    if (RESULTS / "model" / "history.json").exists():
        facts["Val loss"] = f"{json.loads((RESULTS / 'model' / 'history.json').read_text())['best_val']:.3f}"
    facts["Human labels used"] = "0"
    facts["Species"] = focus.label()

    name = f"demo-{slug}-{focus.slug()}.html"
    page = DemoPage(keep, facts, checkpoint=checkpoint).write(RESULTS / name)
    print(f"wrote {page}")
    print(f"   {focus.label()} · {_power_note(len(keep))}")
    if len(keep) < args.n:
        print(f"   only {len(keep)} of the {args.n} asked for exist in the stash; "
              f"`make judge` with a larger --per-species to get more", flush=True)
    print(f"   save the session into {RESULTS / 'listening' / args.model}/")


def trainer(args):
    """The call-type ear trainer — quiz mode only, writes no labels."""
    from crowgpt.trainer import build_trainer

    out = Path(args.out) if args.out else RESULTS / "trainer.html"
    path, summary = build_trainer(out, per_class=args.per_class,
                                  field_per_class=args.field_per_class,
                                  seed=args.seed)
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
    for key, tiers in summary["per_class"].items():
        tally = " · ".join(f"{n} {tier}" for tier, n in sorted(tiers.items()))
        print(f"   {key:<14} {tally}")
    for key, n in summary["excluded_thin"].items():
        print(f"   {key:<14} excluded — only {n} exemplar(s), too thin to quiz")
    print(f"   save sittings into {RESULTS / 'trainer'}/")


def listen(args):
    """What every recorded sitting adds up to, pooled by checkpoint."""
    from crowgpt.listen import ListeningLog

    report = ListeningLog(RESULTS / "listening").report()
    if not report:
        sys.exit(f"no sessions in {RESULTS / 'listening'} — open a demo page, "
                 f"answer some trials, and save the file there")

    print(f"\n{'model':<22} {'n':>5} {'sittings':>9} {'correct':>20} {'d-prime':>8} "
          f"{'bias':>7}  verdict")
    for row in report:
        result = row["discrimination"]
        low, high = result.ci
        rate = f"{result.rate:.1%} [{low:.0%},{high:.0%}]"
        print(f"{row['model']:<22} {result.n:>5} {row['sessions']:>9} {rate:>20} "
              f"{result.dprime:>8.2f} {result.criterion:>7.2f}  {result.verdict}")

    for row in report:
        if not args.detail:
            continue
        print(f"\n{row['model']} ({row['fingerprint']})")
        for species, result in row["discrimination"].by_species().items():
            low, high = result.ci
            print(f"   {species:<20} {result.n:>4} trials  {result.rate:.1%} "
                  f"[{low:.0%},{high:.0%}]")
        seconds = row["discrimination"].decision_seconds()
        if seconds == seconds:
            print(f"   median decision {seconds:.1f}s")
        for note in row["notes"]:
            print(f"   note: {note}")

    print("\nchance is the target: the model wins when the interval covers 50%"
          " and is narrow enough to mean it")


def compare(args):
    """Real / through-the-codec / generated, labelled, for diagnosis by ear.

    Answers the question the listening test cannot: when the output sounds
    rough, is the tokenizer already rough before the model touches it?
    """
    import numpy as np

    from crowgpt.codec import normalise
    from crowgpt.corpus import Corpus
    from crowgpt.demo import ComparePage
    from crowgpt.judge import Ambience, BirdNetJudge
    from crowgpt.sample import Sampler
    from crowgpt.tokens import BoutStore, TokenDataset

    sampler = Sampler(RESULTS / "model" / "model.pt", token_dir=TOKENS)
    store, test = BoutStore(BOUTS), TokenDataset(TOKENS, "test")
    judge = BirdNetJudge()
    ambience = Ambience([r for recs in Corpus().recordings().values() for r in recs[:3]])

    held = {row["group_key"] for row in test.records}
    rng = np.random.default_rng(0)
    by_species = {}
    for row in store.index:
        if row["group_key"] in held and row["n_samples"] > 24000 * 1.5:
            by_species.setdefault(row["species"], []).append(row)

    rows = []
    for i, slug in enumerate(sorted(by_species)[: args.n]):
        picks = by_species[slug]
        row = picks[int(rng.integers(len(picks)))]
        real = normalise(store.audio(row))
        treatments = (
            ("Real", "untouched", real),
            ("Through the codec", "no model involved", sampler.codec.roundtrip(real)[0][: real.size]),
            ("Generated", "the model", sampler.audio(slug, seed=100 + i)),
        )
        arms = []
        for label, note, samples in treatments:
            placed = ambience.place(samples)
            arms.append((label, note, placed, round(judge.confidence(placed)[0], 3)))
        rows.append({"species": slug, "arms": arms})
        print(f"   {slug}: " + "  ".join(f"{a[0]} {a[3]}" for a in arms), flush=True)

    facts = {"Codec": f"EnCodec {sampler.manifest['bandwidth']:g} kbps"}
    if (RESULTS / "judge.json").exists():
        judged = json.loads((RESULTS / "judge.json").read_text())
        facts["Real detected"] = f"{judged['A_real']['detected_rate']:.0%}"
        facts["Codec ceiling"] = f"{judged['B_real_codec']['detected_rate']:.0%}"
        facts["Generated detected"] = f"{judged['C_generated']['detected_rate']:.0%}"
    print(f"wrote {ComparePage(rows, facts).write(RESULTS / 'compare.html')}")


def evaluate(args):
    """Compare models on matched conditions, with error bars.

    Replaces the judge whose two readings of one model came back 50.0% and
    31.7%. Same conditions for every model, bootstrap intervals on every number,
    and a Fréchet distance in two embedding spaces.
    """
    import numpy as np

    from crowgpt.corpus import Corpus
    from crowgpt.embed import AstEmbedder, BirdNetEmbedder
    from crowgpt.evaluate import Conditions, Evaluation, compare
    from crowgpt.judge import Ambience, BirdNetJudge
    from crowgpt.sample import Sampler

    wanted = args.models or ["model-long", "model-d256-6k", "model-d384-12k"]
    available = [(n, RESULTS / n) for n in wanted if (RESULTS / n / "model.pt").exists()]
    if not available:
        sys.exit(f"no checkpoints among {wanted}")

    judge = BirdNetJudge()
    ambience = Ambience([r for recs in Corpus().recordings().values() for r in recs[:4]])
    first = Sampler(available[0][1] / "model.pt", token_dir=TOKENS)
    conditions = Conditions(first.species, per_species=args.per_species)
    print(f"   {len(conditions)} matched conditions x {len(available)} models", flush=True)

    evaluation = Evaluation(BOUTS, TOKENS, ambience, judge,
                            [BirdNetEmbedder(), AstEmbedder()], conditions)
    results = {}

    print("   real arm", flush=True)
    real = evaluation.real_arm()
    real_conf = evaluation.score(real)
    reference = evaluation.embed_reference(real)
    results["A real"] = evaluation.summarise("A real", real_conf, real)
    results["A real"]["mean_conf_values"] = real_conf

    print("   codec arm", flush=True)
    coded = evaluation.codec_arm(first.codec, real)
    coded_conf = evaluation.score(coded)
    results["B codec"] = evaluation.summarise("B codec", coded_conf, coded, reference)
    results["B codec"]["mean_conf_values"] = coded_conf

    for name, folder in available:
        print(f"   {name}", flush=True)
        tokens = TOKENS.parent / "tokens-12k" if "12k" in name else TOKENS
        sampler = Sampler(folder / "model.pt", token_dir=tokens)
        clips = evaluation.model_arm(sampler)
        conf = evaluation.score(clips)
        results[name] = evaluation.summarise(name, conf, clips, reference)
        results[name]["mean_conf_values"] = conf

    results["_paired"] = compare({k: v for k, v in results.items() if not k.startswith("_")})
    (RESULTS / "evaluation.json").write_text(json.dumps(results, indent=2, default=lambda o: None))
    _report_evaluation(results)


def _report_evaluation(results):
    print(f"\n{'arm':<18} {'mean conf':>18} {'detected':>18} {'FAD birdnet':>12} {'FAD ast':>9}")
    for name, row in results.items():
        if name.startswith("_"):
            continue
        conf = f"{row.get('mean_conf', 0):.3f} [{row['mean_conf_ci'][0]:.2f},{row['mean_conf_ci'][1]:.2f}]"
        det = f"{row.get('detected_rate', 0):.1%} [{row['detected_ci'][0]:.0%},{row['detected_ci'][1]:.0%}]"
        fad = row.get("fad", {})
        print(f"{name:<18} {conf:>18} {det:>18} "
              f"{fad.get('birdnet', float('nan')):>12.1f} {fad.get('ast', float('nan')):>9.1f}")
    paired = results.get("_paired") or {}
    if paired.get("against"):
        print(f"\npaired against {paired['best']}, on identical conditions:")
        for name, diff in paired["against"].items():
            verdict = "REAL" if diff["significant"] else "inside the noise"
            print(f"   {name:<18} {diff['mean_difference']:+.3f} "
                  f"[{diff['ci'][0]:+.3f},{diff['ci'][1]:+.3f}]  {verdict}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crowgpt", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="stage", required=True)

    p = sub.add_parser("extract", help="corpus -> call bouts on disk")
    p.add_argument("--limit", type=int, default=None, help="recordings per species")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--out", default=None,
                   help=f"bout store dir (default {BOUTS}); a variant corpus "
                        "like the 0067 long-context store must not overwrite "
                        "the standing one")
    p.set_defaults(func=extract)

    p = sub.add_parser("gate", help="can a neural codec carry a caw?")
    p.add_argument("--per-species", type=int, default=50)
    p.set_defaults(func=gate)

    p = sub.add_parser("tokenize", help="bouts -> token memmaps")
    p.add_argument("--bandwidth", type=float, default=6.0)
    p.add_argument("--keep", type=int, default=None,
                   help="keep only the first K codebooks (default: all for the bandwidth)")
    p.add_argument("--out", default=None, help=f"token dir (default {TOKENS})")
    p.add_argument("--codec", default="encodec", choices=("encodec", "dac-24khz", "dac-44khz"),
                   help="tokenizer; dac uses --keep as its codebook count (0034: dac-24khz at 24)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-augment", action="store_true")
    # EXPOSED BECAUSE THE DEFAULT SILENTLY CHANGED THE CORPUS SIZE. TokenWriter
    # defaults to 8 sub-hop variants, and the comment beside that default says
    # eight "was right for 25k bouts" and costs only tokenising time on a larger
    # one — so the standing token set was written with 2 and the CLI, which never
    # exposed the knob, produced 8. That is a 4x difference in apparent corpus
    # size made entirely of near-duplicates, which is exactly the quantity a
    # scaling curve must not be fooled by.
    p.add_argument("--variants", type=int, default=2,
                   help="sub-hop augmentation per bout (default 2, matching the "
                        "standing token set; TokenWriter's own default is 8)")
    p.add_argument("--units", action="store_true",
                   help="add the units-per-bout conditioning token (0066): the "
                        "segmenter counts caws per bout at tokenize time and "
                        "generation samples the count like the duration bucket")
    p.add_argument("--bouts", default=None,
                   help=f"bout store to read (default {BOUTS})")
    p.add_argument("--call-types", default=None,
                   help="call_types.json from `label-calltypes`; adds the "
                        "call-type prefix token (0021). Must have been built "
                        "for this exact bout store — the file is positional")
    p.set_defaults(func=tokenize)

    p = sub.add_parser("label-calltypes",
                       help="pseudo-label a bout store with call types (0021's "
                            "uncommitted step, made a stage)")
    p.add_argument("--bouts", default=None,
                   help=f"bout store to read (default {BOUTS})")
    p.add_argument("--out", default=None,
                   help="output JSON (default <bouts>/call_types.json)")
    p.add_argument("--species", default="american-crow",
                   help="only this species is labelled; the rest tokenize as "
                        "unknown (the human labels are American Crow only)")
    p.add_argument("--seed", type=int, default=0,
                   help="split seed — must match tokenize's, or the head sees "
                        "held-out recordings")
    p.set_defaults(func=label_calltypes)

    p = sub.add_parser("latents", help="bouts -> continuous DAC latent memmaps")
    p.add_argument("--stages", type=int, default=32,
                   help="RVQ stages in the cascade; 32 x 8 = 256 dims (0052)")
    p.add_argument("--species", default="american-crow")
    p.add_argument("--all-species", action="store_true",
                   help="encode every species (0049 found the other 45 neutral)")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--out", default=None, help="latent dir (default DATA/latents)")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=latents)

    p = sub.add_parser("train", help="train the model")
    p.add_argument("--steps", type=int, default=6000)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--dropout", type=float, default=0.25)
    p.add_argument("--n-embd", type=int, default=256)
    p.add_argument("--n-layer", type=int, default=6)
    p.add_argument("--token-dir", default=None, help=f"tokens to train on (default {TOKENS})")
    p.add_argument("--out", default=None, help="checkpoint dir (default results/model)")
    # The constant that silently clipped a requested batch of 32 to 14 for a
    # whole project, and to ~4 at sixteen codebooks. A flag so a run can say
    # what it meant rather than discovering the batch it actually got.
    p.add_argument("--memory-budget", type=int, default=240_000_000)
    p.add_argument("--accumulate", type=int, default=1,
                   help="micro-steps per optimiser step; effective batch is batch-size x this")
    p.add_argument("--block-size", type=int, default=None,
                   help="cap on sequence length (default 4096; 24 codebooks needs 6144)")
    p.add_argument("--loss-from-stage", type=int, default=None,
                   help="score only codebooks >= this; the extender's knob (WP2)")
    p.add_argument("--channels", default=None,
                   help="channels.json from `channels`; adds the channel prefix token")
    p.set_defaults(func=train)

    p = sub.add_parser("flow-train", help="train the rectified-flow DiT on latents")
    p.add_argument("--steps", type=int, default=30000)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--eval-every", type=int, default=500)
    p.add_argument("--n-layer", type=int, default=8)
    p.add_argument("--n-head", type=int, default=6)
    p.add_argument("--n-embd", type=int, default=None,
                   help="width; leave unset for the default config")
    p.add_argument("--dropout", type=float, default=0.0)
    p.add_argument("--max-frames", type=int, default=256)
    p.add_argument("--normalisation", default="global", choices=("global", "per_channel"),
                   help="global keeps the RVQ's own variance decay, which is the "
                        "perceptual importance ordering; per_channel whitens it away "
                        "and was how the first 0054 run scored 25%%")
    p.add_argument("--t-sampling", default="logit_normal",
                   choices=("logit_normal", "uniform"),
                   help="where along the path training signal goes; uniform "
                        "under-trains the noise end where global structure is "
                        "decided (0054)")
    p.add_argument("--t-mean", type=float, default=-0.5,
                   help="logit-normal mean; NEGATIVE pulls training toward the "
                        "noise end, where 0054 localised the failure")
    p.add_argument("--latent-dir", default=None)
    p.add_argument("--out", default=None, help="checkpoint dir (default RESULTS/model-flow)")
    p.set_defaults(func=flow_train)

    p = sub.add_parser("flow-sample", help="generate wavs from the flow model")
    p.add_argument("--count", type=int, default=16)
    p.add_argument("--steps", type=int, default=32, help="Euler steps for the ODE")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--model", default=None)
    p.add_argument("--latent-dir", default=None)
    p.add_argument("--out", default=None)
    p.set_defaults(func=flow_sample)

    p = sub.add_parser("channels", help="cluster recordings into channel buckets")
    p.add_argument("--buckets", type=int, default=256)
    p.add_argument("--per-recording", type=int, default=4)
    p.add_argument("--out", default=None)
    p.set_defaults(func=channels)

    p = sub.add_parser("sample", help="generate wavs")
    p.add_argument("-n", type=int, default=8, help="per species")
    p.add_argument("--temperature", type=float, default=1.0,
                   help="re-measured on the d384-6k model; see sample.py")
    p.set_defaults(func=sample)

    p = sub.add_parser("judge", help="four-arm BirdNET judgement + memorisation")
    p.add_argument("--per-species", type=int, default=12)
    p.set_defaults(func=judge)

    p = sub.add_parser("demo", help="write the listening-test page")
    p.add_argument("-n", type=int, default=60, help="trials")
    p.add_argument("--model", default="model-d384-6k",
                   help="checkpoint the sitting judges; its hash keys the session")
    p.add_argument("--species", default=None,
                   help="focus species, comma separated, or `all` (default: american-crow)")
    p.add_argument("--generate", action="store_true",
                   help="make a fresh focused set on matched conditions (needs the GPU)")
    p.add_argument("--against", default=None,
                   help="second checkpoint; builds ONE sitting judging both, "
                        "which is the only way to compare two without measuring "
                        "the listener in between")
    p.add_argument("--stash", action="store_true",
                   help="use the judge's six-species stash instead of a focused set")
    p.set_defaults(func=demo)

    p = sub.add_parser("listen", help="what the recorded listening sessions add up to")
    p.add_argument("--detail", action="store_true", help="per species, timings and notes")
    p.set_defaults(func=listen)

    p = sub.add_parser("evaluate", help="compare models on matched conditions, with error bars")
    p.add_argument("--models", nargs="*", default=None)
    p.add_argument("--per-species", type=int, default=12)
    p.set_defaults(func=evaluate)

    p = sub.add_parser("compare", help="real vs codec vs generated, labelled")
    p.add_argument("-n", type=int, default=6, help="species")
    p.set_defaults(func=compare)

    p = sub.add_parser("trainer", help="the call-type ear trainer (quiz only)")
    p.add_argument("--per-class", type=int, default=12,
                   help="exemplars per call type")
    p.add_argument("--field-per-class", type=int, default=3,
                   help="cap on the recordist's own labels per class")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=None,
                   help="output HTML (default results/trainer.html)")
    p.set_defaults(func=trainer)

    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
