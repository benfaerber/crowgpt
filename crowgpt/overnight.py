"""The unattended run: re-extract the grown corpus, sweep capacity, judge, demo.

Start it and go to bed. It reports continuously through crowgpt.progress.Run —
stage, how far in, an ETA computed from its own measured rate, and any finding
worth seeing without opening anything else. `make -C crowgpt watch` (or the
dashboard's Training panel) is the whole status interface.

    make -C crowgpt overnight              # the default plan, roughly 8 hours
    make -C crowgpt overnight HOURS=6      # trims the sweep to fit
    make -C crowgpt overnight SKIP=extract # reuse the bouts already on disk

WHAT IT IS FOR. The shipped model saw 12.75 hours of bouts and 6,000 training
steps. Training longer took detection from 38.9% to 61.1% against a codec
ceiling of 81.9%, so the model — not the tokenizer and not the data pipeline —
was the binding constraint. The big archive batch then roughly quintuples the
corpus. This asks what the two together are worth, and whether more capacity
helps once there is more to learn from.

WHAT IT WILL NOT DO. It will not touch results/model/, which is what the
published demo plays, until the run is over and a candidate has actually beaten
it on the four arms. A worse model is a real outcome and it must not overwrite a
better one at 3am.

SAFE TO INTERRUPT. Ctrl-C, a reboot, an OOM: every stage checks for its own
output first, so re-running resumes rather than restarting. The one stage worth
knowing about is extract, which rewrites the bout shards from scratch — if it is
interrupted, delete data/crowgpt/bouts and let it run again.
"""

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

# BEFORE anything that can import birdnetlib. Loading it first makes torch
# permanently blind to the GPU in this process — see crowgpt/gpu.py.
from crowgpt.gpu import claim  # noqa: E402

claim()

from crowgpt.progress import Run  # noqa: E402
from crowgpt.train import NoGpu, require_device  # noqa: E402

REPO = HERE.parent
DATA = REPO / "data" / "crowgpt"
BOUTS, TOKENS = DATA / "bouts", DATA / "tokens"
RESULTS = HERE / "results"
PROGRESS_HINT = "make -C crowgpt watch"


def relocate(root):
    """Point every output at a throwaway root, for --check.

    The check has to exercise the real stages against real audio — a rehearsal
    on synthetic tones proves the plumbing and not much else — so it runs the
    same code and only changes where the results land.
    """
    global BOUTS, TOKENS, RESULTS
    root = Path(root)
    BOUTS, TOKENS, RESULTS = root / "bouts", root / "tokens", root / "results"
    RESULTS.mkdir(parents=True, exist_ok=True)
    return root

# Capacity ladder. The shipped model is the first rung, so the sweep answers
# "does more capacity help on a bigger corpus" rather than assuming it does.
# Ordered smallest first: if the night runs short, the cheap informative runs
# have already finished.
# Ordered by what the night most needs to answer, not by cost, because the
# budget check drops from the end and the last rung is the one most likely to
# be lost.
LADDER = [
    # 1. The shipped architecture on the bigger corpus: what is the data alone
    #    worth, with nothing else changed? Cheapest and the necessary baseline.
    {"name": "d256-6k", "n_embd": 256, "n_layer": 6, "n_head": 4, "bandwidth": 6.0},
    # 2. The scratchiness test, and the reason it outranks capacity: "still
    #    scratchy, but now it sounds like a robo crow" says structure is being
    #    learned and fine detail is not, and fine detail is what the late
    #    residual codebooks carry. Sixteen instead of eight. 0014 measured the
    #    codec ceiling rising 0.810 -> 0.877 here.
    {"name": "d384-12k", "n_embd": 384, "n_layer": 8, "n_head": 6, "bandwidth": 12.0},
    # 3. Capacity at the current bitrate. The most speculative of the three, so
    #    it is the one to lose if the night runs short.
    {"name": "d384-6k", "n_embd": 384, "n_layer": 8, "n_head": 6, "bandwidth": 6.0},
]
STAGES = ["extract"] + [s for c in LADDER for s in (
    f"tokenize {c['bandwidth']:g}k", f"train {c['name']}", f"judge {c['name']}")] + \
    ["compare", "demo"]
STAGES = list(dict.fromkeys(STAGES))


def hours(seconds):
    return seconds / 3600.0


class AlreadyRunning(RuntimeError):
    pass


class Lock:
    """One run per output directory.

    Two runs sharing a scratch directory overwrite each other's bouts, tokens
    and checkpoints, and both write the same progress record, so it alternates
    between two different truths and neither result means anything. Easy to do by
    accident — start it, forget, start it again — and it looks like a slow run
    rather than a broken one.
    """

    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            pid = self.path.read_text().strip()
            if _alive(pid):
                raise AlreadyRunning(
                    f"another run is already going (pid {pid}). Watch it with "
                    f"`{PROGRESS_HINT}`, or stop it first."
                )
            print(f"clearing a stale lock from pid {pid}\n")
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


def _alive(pid):
    try:
        os.kill(int(pid), 0)
    except (ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True
    return True


class Overnight:
    def __init__(self, args):
        self.args = args
        self.skip = set(args.skip.split(",")) if args.skip else set()
        self.run = Run("CROWGPT — OVERNIGHT RUN", STAGES)
        self.started = time.monotonic()
        self.scores = {}

    def spent(self):
        return hours(time.monotonic() - self.started)

    def left(self):
        return self.args.budget_hours - self.spent()

    # ---- stages -------------------------------------------------------

    def extract(self):
        # Through the subprocess, not by importing Extractor here: it pulls
        # birdnetlib, and this process needs the GPU for every later stage.
        from crowgpt.birdnet import BirdNet

        with self.run.stage("extract") as stage:
            summary = self._existing_bouts()
            if summary and ("extract" in self.skip or not self._corpus_grew(summary)):
                stage.say(f"reused {summary['kept']} bouts, {summary['hours']:.1f} h")
                return summary
            if summary:
                self.run.note(f"re-extracting: the corpus has grown past the "
                              f"{summary['recordings']} recordings the bouts were cut from")
            stage.say("reading the corpus through BirdNET (CPU-bound, the long one)")
            stage.say("running BirdNET in a subprocess (watch the count below)")
            summary = BirdNet().extract(BOUTS, limit=self.args.limit_per_species,
                                        workers=self.args.workers)
            stage.say(f"{summary['kept']} bouts, {summary['hours']:.1f} h, "
                      f"{summary['errors']} unreadable")
            self.run.note(f"corpus: {summary['kept']} bouts / {summary['hours']:.1f} h "
                          f"from {summary['recordings']} recordings")
            mix = summary.get("per_species", {})
            if mix:
                biggest = max(mix.items(), key=lambda kv: kv[1]["bouts"])
                share = biggest[1]["bouts"] / summary["kept"]
                self.run.note(f"species mix: {biggest[0]} is {share:.0%} of it "
                              f"(sampling balance={self.args.balance})")
            return summary

    def token_dir(self, bandwidth):
        """One directory per bandwidth — 8 and 16 codebooks are different vocabularies."""
        return TOKENS if bandwidth == 6.0 else TOKENS.parent / f"tokens-{bandwidth:g}k"

    def _variants_for(self, bouts):
        """Sub-hop augmentation, scaled to how much real audio there is.

        Eight variants was right for 25,000 bouts. The corpus has since taken
        the corpus past 100,000, where augmentation is mostly buying tokenising
        hours rather than variety — and tokenising is the second longest stage
        in the night. One variant of 150,000 real bouts is already more
        sequences than eight variants of the old corpus.
        """
        asked = self.args.variants
        if bouts >= 100_000:
            return 1
        if bouts >= 50_000:
            return min(asked, 2)
        return asked

    @staticmethod
    def _existing_bouts():
        """A previous extract's summary, only if the shards still match it.

        summary.json is written last, so a killed extract leaves the PREVIOUS
        summary next to half-written shards — it claimed 25,227 bouts while the
        shards held one species and four empty files. Reusing that trains on
        whatever survived and reports the old number, which is the worst
        outcome available. We were saved here only by the corpus having grown.
        """
        path = BOUTS / "summary.json"
        index = BOUTS / "index.jsonl"
        if not path.exists():
            return None
        summary = json.loads(path.read_text())
        if not index.exists():
            return None
        with open(index) as handle:
            rows = sum(1 for line in handle if line.strip())
        if rows != summary.get("kept"):
            print(f"   ignoring summary.json: it claims {summary.get('kept')} bouts "
                  f"but index.jsonl holds {rows} — a previous extract was interrupted",
                  flush=True)
            return None
        return summary

    def _corpus_grew(self, summary):
        """Has audio arrived since the bouts were cut?

        The whole point of an overnight run is that a download finished during
        the evening, and --reuse would otherwise skip extraction and quietly
        train on yesterday's corpus. Counting recordings is cheap; being wrong
        about it costs the entire night.
        """
        if not self.args.reuse:
            return True
        from crowgpt.corpus import Corpus

        now = sum(len(v) for v in Corpus().recordings().values())
        return now > summary.get("recordings", 0)

    def tokenize(self, bandwidth):
        from crowgpt.tokens import BoutStore, TokenWriter

        name = f"tokenize {bandwidth:g}k"
        out = self.token_dir(bandwidth)
        with self.run.stage(name) as stage:
            fresh_bouts = (BOUTS / "index.jsonl").stat().st_mtime if (BOUTS / "index.jsonl").exists() else 0
            usable = (out / "manifest.json").exists() and \
                     (out / "manifest.json").stat().st_mtime > fresh_bouts
            if name in self.skip or (self.args.reuse and usable):
                manifest = json.loads((out / "manifest.json").read_text())
                stage.say(f"reused {manifest['splits']['train']['sequences']} train sequences")
                return out
            if (out / "manifest.json").exists():
                self.run.note(f"re-tokenising {bandwidth:g}k: the bouts are newer than the tokens")
            # Tokenising at 16 codebooks is hours. Starting one with two left
            # burns the rest of the night on a stage that cannot finish.
            need = self.args.reserve_hours + (3.0 if bandwidth > 6.0 else 1.5)
            if self.left() < need:
                stage.say(f"skipped — {self.left():.1f} h left, needs about {need:.1f}")
                return None
            store = BoutStore(BOUTS)
            splits = store.split(seed=0)
            variants = self._variants_for(len(store))
            stage.say(f"{len(store)} bouts at {bandwidth:g} kbps, {variants} variants")
            manifest = TokenWriter(store, out, bandwidth=bandwidth,
                                   variants=variants).run(splits)
            self.run.note(f"tokens at {bandwidth:g} kbps: "
                          f"{manifest['splits']['train']['sequences']} sequences, "
                          f"{manifest['splits']['train']['tokens']:,} tokens, "
                          f"K={manifest['n_codebooks']}")
            return out

    def train(self, config, token_dir):
        from crowgpt.train import Trainer

        name = f"train {config['name']}"
        out = RESULTS / f"model-{config['name']}"
        with self.run.stage(name) as stage:
            if token_dir is None:
                stage.say("skipped — its tokens were never built")
                return None
            # history.json is written only when training completes, so it is the
            # proof that model.pt is finished rather than a mid-run checkpoint.
            # The killed CPU run left a model.pt from step 1,500 of 40,000, and
            # reusing that would have judged a barely-trained model and reported
            # the number as the answer.
            if self.args.reuse and (out / "history.json").exists():
                best = json.loads((out / "history.json").read_text())["best_val"]
                stage.say(f"reused a completed checkpoint (val {best:.4f})")
                return out
            if (out / "model.pt").exists():
                self.run.note(f"discarding {config['name']}: a checkpoint exists but "
                              "training never finished, so it is mid-run")
                shutil.rmtree(out, ignore_errors=True)
            if self.left() < self.args.reserve_hours:
                stage.say(f"skipped — only {self.left():.1f} h left, "
                          f"reserving {self.args.reserve_hours} h for judging")
                return None
            shape = {k: v for k, v in config.items() if k not in ("name", "bandwidth")}
            trainer = Trainer(token_dir, out, steps=self.args.steps,
                              balance=self.args.balance, **shape)
            params = trainer.model.n_params() / 1e6
            stage.say(f"{params:.1f}M params, {self.args.steps} steps")

            history = trainer.run(on_eval=lambda step, val: stage.update(
                step, self.args.steps, extra=f"{params:.0f}M params, val {val:.4f}"))
            self.run.note(f"{config['name']}: {params:.1f}M params, "
                          f"best val {history['best_val']:.4f}")
            return out

    def judge(self, config, checkpoint, token_dir):
        from crowgpt.corpus import Corpus
        from crowgpt.judge import Judgement
        from crowgpt.sample import Sampler

        name = f"judge {config['name']}"
        with self.run.stage(name) as stage:
            if token_dir is None or checkpoint is None or not (checkpoint / "model.pt").exists():
                stage.say("skipped — no checkpoint")
                return None
            stage.say("generating and scoring four arms")
            sampler = Sampler(checkpoint / "model.pt", token_dir=token_dir)
            # Judging at 16 codebooks costs twice the forward passes per bout,
            # and an underfit model never stops early, so it runs to the cap
            # every time. Left equal, this stage alone eats the reserve.
            per_species = self.args.judge_n
            if config.get("bandwidth", 6.0) > 6.0:
                per_species = max(4, per_species // 2)
            judgement = Judgement(sampler, token_dir, BOUTS, per_species=per_species,
                                  max_frames=self.args.max_frames)
            ambience = [r for recs in Corpus().recordings().values() for r in recs[:6]]
            results, clips = judgement.run(ambience)
            (checkpoint / "judge.json").write_text(json.dumps(results, indent=2))

            generated = results["C_generated"]["detected_rate"]
            ceiling = results["B_real_codec"]["detected_rate"]
            self.scores[config["name"]] = {"detected": generated, "ceiling": ceiling,
                                           "path": checkpoint, "clips": clips}
            stage.say(f"generated {generated:.1%} against a {ceiling:.1%} ceiling")
            # A zero ceiling means BirdNET heard nothing even in real audio —
            # impossible on the real corpus, routine on a synthetic one, and not
            # a reason to end the night.
            share = f"{generated / ceiling:.0%} of what the codec allows" if ceiling else \
                    "ceiling is zero — BirdNET heard nothing in the real arm either"
            self.run.note(f"{config['name']}: generated {generated:.1%}, "
                          f"ceiling {ceiling:.1%}, {share}")
            return results

    def compare(self):
        with self.run.stage("compare") as stage:
            if not self.scores:
                stage.say("nothing to compare — every training run was skipped")
                return None
            # The bar to beat is the best score any model has ever posted, not
            # whatever happens to sit in results/model/. The old lookup pointed
            # at results/model/judge.json, which nothing had ever written — so
            # the baseline was always 0.0 and every candidate promoted itself,
            # including one scoring 29%.
            # Exclude this run's own results, or the winner is compared against
            # itself and can never promote. The last run reported "d256-6k did
            # not beat the shipped 66.7%" where the 66.7% WAS d256-6k.
            mine = {str((s["path"] / "judge.json").resolve()) for s in self.scores.values()}
            baseline, holder = 0.0, "nothing"
            candidates = [p for p in sorted(RESULTS.glob("judge*.json"))
                          + sorted(RESULTS.glob("model-*/judge.json"))
                          if str(p.resolve()) not in mine]
            for path in candidates:
                try:
                    score = json.loads(path.read_text())["C_generated"]["detected_rate"]
                except (ValueError, KeyError):
                    continue
                if score > baseline:
                    baseline, holder = score, path.parent.name if path.parent != RESULTS else path.stem
            stage.say(f"best so far is {holder} at {baseline:.1%}")
            if getattr(self.args, "check", False):
                # A forty-step model scores zero and would never promote, leaving
                # the one destructive path in the run untested by the very thing
                # meant to test it.
                baseline = -1.0
            winner = max(self.scores.items(), key=lambda kv: kv[1]["detected"])
            name, score = winner
            stage.say(f"best of this run is {name} at {score['detected']:.1%} "
                      f"(best ever: {holder} at {baseline:.1%})")
            self.run.note("RESULTS, best last:\n" + "\n".join(
                f"    {n:<10} {s['detected']:.1%} of {s['ceiling']:.1%} ceiling"
                for n, s in sorted(self.scores.items(), key=lambda kv: kv[1]["detected"])))
            if score["detected"] <= baseline:
                self.run.note(f"NOT promoting: {name} did not beat the shipped "
                              f"{baseline:.1%}. results/model/ is untouched.")
                return None
            self.run.note(f"promoting {name} -> results/model/ "
                          f"({baseline:.1%} -> {score['detected']:.1%})")
            return winner

    def demo(self, winner):
        from crowgpt.cli import _balanced
        from crowgpt.demo import DemoPage

        with self.run.stage("demo") as stage:
            if not winner:
                stage.say("skipped — nothing beat the shipped model")
                return
            name, score = winner
            backup = promote(score["path"], RESULTS / "model")

            clips = score["clips"]
            keep = _balanced(clips, self.args.demo_n)
            facts = {"Detected": f"{score['detected']:.0%}",
                     "Codec ceiling": f"{score['ceiling']:.0%}",
                     "Model": name, "Human labels used": "0"}
            if (BOUTS / "summary.json").exists():
                summary = json.loads((BOUTS / "summary.json").read_text())
                facts["Training bouts"] = f"{summary['kept']:,}"
                facts["Hours"] = f"{summary['hours']:.1f}"
            page = DemoPage(keep, facts).write(RESULTS / "demo.html")
            stage.say(f"wrote {page.name} from {name}")
            self.run.note(f"previous model kept at {backup.name}/ in case you disagree")

    # ---- driver -------------------------------------------------------

    def go(self):
        try:
            self.extract()
            # Judge each model as soon as it trains, not after all of them.
            # Batching the judging to the end means a night that overruns — and
            # this one will, the corpus came in bigger than planned — leaves
            # trained checkpoints on disk with no verdict on any of them, which
            # is the one thing the morning actually needs.
            for config in LADDER:
                token_dir = self.tokenize(config["bandwidth"])
                checkpoint = self.train(config, token_dir)
                try:
                    self.judge(config, checkpoint, token_dir)
                except Exception as exc:  # noqa: BLE001 — one bad judge must not end the night
                    self.run.failed(f"judge {config['name']}", exc)
            self.demo(self.compare())
        except Exception as exc:  # noqa: BLE001
            self.run.note("RUN ABORTED\n" + traceback.format_exc())
            raise
        finally:
            self.run.note(f"finished after {self.spent():.1f} h")


def promote(candidate, live):
    """Replace the live model with a candidate, keeping the old one.

    Separated out and tested because this is the only thing in the run that
    destroys something: it deletes whatever the published demo is currently
    playing. The previous model is copied aside first, and the candidate is
    checked before anything is removed — an unreadable candidate must leave the
    live model exactly where it was rather than deleting it and then failing.
    """
    candidate, live = Path(candidate), Path(live)
    if not (candidate / "model.pt").exists():
        raise FileNotFoundError(f"{candidate} has no model.pt — refusing to promote")

    backup = live.parent / "model-previous"
    if live.exists():
        shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(live, backup)
    staging = live.parent / "model-incoming"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(candidate, staging)
    shutil.rmtree(live, ignore_errors=True)
    staging.rename(live)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--budget-hours", type=float, default=10.0)
    parser.add_argument("--reserve-hours", type=float, default=1.0,
                        help="time held back so judging always happens")
    parser.add_argument("--steps", type=int, default=40000)
    parser.add_argument("--variants", type=int, default=3,
                        help="sub-hop augmentation; 8 was for a corpus 5x smaller")
    parser.add_argument("--balance", type=float, default=0.0,
                        help="0 = corpus proportions (an American Crow model), "
                             "1 = every species equally")
    # Extract is the longest stage and it is BirdNET on the CPU, one model per
    # worker. The old default of 12 left two thirds of a 32-thread machine idle
    # for three hours; each worker is a few hundred MB against 62 GB of RAM.
    parser.add_argument("--workers", type=int,
                        default=max(4, min(24, (os.cpu_count() or 8) - 4)))
    parser.add_argument("--judge-n", type=int, default=12, help="bouts per species per arm")
    parser.add_argument("--max-frames", type=int, default=225,
                        help="cap generated bout length; 225 is a full 3 seconds")
    parser.add_argument("--demo-n", type=int, default=24)
    parser.add_argument("--limit-per-species", type=int, default=None,
                        help="cap recordings read per species (the check uses this)")
    parser.add_argument("--scratch", default=None,
                        help="write bouts/tokens/results here instead of in place")
    parser.add_argument("--check", action="store_true",
                        help="run every stage tiny, on real audio, touching nothing real")
    parser.add_argument("--skip", default="", help="comma-separated stage names")
    parser.add_argument("--reuse", action="store_true", default=True,
                        help="reuse any stage output already on disk")
    parser.add_argument("--fresh", dest="reuse", action="store_false")
    args = parser.parse_args()
    if args.check:
        args.scratch = args.scratch or (HERE / ".check")
        args.limit_per_species = args.limit_per_species or 3
        args.steps, args.variants = 40, 2
        args.judge_n, args.demo_n = 1, 4
        args.max_frames = 32  # ~0.4 s — enough to prove the path, not to hear it
        args.budget_hours, args.reserve_hours = 99.0, 0.0
        args.reuse = False
        global LADDER, STAGES
        LADDER = [
            {"name": "check-6k", "n_embd": 64, "n_layer": 2, "n_head": 2, "bandwidth": 6.0},
            {"name": "check-12k", "n_embd": 64, "n_layer": 2, "n_head": 2, "bandwidth": 12.0},
        ]
        STAGES = ["extract"] + [s for c in LADDER for s in (
            f"tokenize {c['bandwidth']:g}k", f"train {c['name']}",
            f"judge {c['name']}")] + ["compare", "demo"]
    # Fail before doing three hours of extraction that ends at a GPU stage.
    try:
        require_device()
    except NoGpu as exc:
        sys.exit(f"refusing to start: {exc}")

    if args.scratch:
        root = relocate(args.scratch)
        print(f"scratch run — everything lands under {root}, nothing real is touched\n")

    try:
        with Lock(RESULTS / ".overnight.lock"):
            run = Overnight(args)
            run.go()
    except AlreadyRunning as exc:
        sys.exit(f"refusing to start: {exc}")

    if args.check:
        failed = [n for n, s in run.run.state.items() if s["status"] != "done"]
        if failed:
            print("\nCHECK FAILED — these stages did not complete:")
            for name in failed:
                print(f"    {name}: {run.run.state[name]['status']} "
                      f"{run.run.state[name]['note']}")
            print("Full detail in the run's data/progress record.")
            sys.exit(1)
        print("\nCHECK PASSED — all "
              f"{len(STAGES)} stages completed, demo rendered. "
              "`make -C crowgpt overnight` is good to go.")
        sys.exit(0)


if __name__ == "__main__":
    main()
