"""Is a continuous DAC latent forgiving of error in a way a code index is not?

THE CLAIM UNDER TEST is the founding premise of every "model the latent instead
of the symbol" idea, and it has never been measured here. Stated plainly:

    a discrete code is either right or wrong, and a wrong one is a blip;
    a continuous latent can be approximately right, and approximately right
    is inaudible.

If that is true, the ceiling that 0035 hit is a property of the ENCODING and not
of the audio. 0035 found DAC's stages 8-23 carry 9.935 bits of 10 — unpredictable
as symbol indices, because RVQ scatters near-neighbour vectors across arbitrary
integers, and an extender recovered 0.034 bits and scored 0/24. That wall is real
and permanent in code space. It says nothing about whether the underlying vectors
are predictable, and nobody has asked.

If it is false — if a latent perturbed by plausible model error sounds as broken
as a mis-sampled token — then the whole continuous route is dead and this cost a
day instead of a fortnight.

WHY THIS IS WORTH A SITTING WHEN SIX MODELLING IDEAS HAVE ALREADY FAILED. 0045
closed with "the modelling route is exhausted -- anything further needs a
genuinely new class of idea", after nulls on capacity (0023, 0038), data (0048,
0049, 0050), sequence length (0038), token layout (0045), tokenizer config
(0028-0037), filtering (0027) and the fine-stage extender (0035). Every one of
those varied WHICH discrete tokens. Not one varied WHETHER discrete tokens. The
shape of the null set is itself the argument: when capacity, data, length, layout
and codec are all neutral, what is left is the objective and the representation.

WHAT THIS IS NOT. Gaussian noise is a STAND-IN for model error, not model error.
A trained flow model's residual is correlated across time and channel and may be
systematically biased in ways white noise is not. So this measures whether the
REPRESENTATION is forgiving, which is a precondition, not whether any particular
model will succeed. A pass here does not predict a good generator. A fail here
kills the route outright, and that asymmetry is the whole reason to run it first
and cheap.

THE ARMS BRACKET A KNEE, which is what the bench turned this into.

  cont32          25   the ceiling. The 256-d continuous cascade, no codebook
                       anywhere, decoded. If this is audible the route is dead
                       before error budgets matter.
  cont32+noise.20  25  a model 20% wrong per channel, in units of the corpus's
                       own per-channel spread. The realistic case.
  cont32+noise.40  25  40% wrong. Offline this lands on EnCodec-6k, which 0039
                       could not resolve by ABX either.
  cont32+noise.80  25  80% wrong, and the SECOND CONTROL. Offline it is clear of
                       every codec ever measured in this project. If even this
                       reads chance, latent noise is inaudible at every level
                       tested and the page has no power to locate a budget —
                       which is a different and much less encouraging result than
                       a genuine pass, and nothing else would distinguish them.
  lowpass_2k      20   the anchor, carried over from 0039 unchanged. A 2 kHz
                       lowpass cannot be inaudible. If it does not come out well
                       above chance the page or the playback chain is broken and
                       nothing on it is readable. Never a codec, for 0039's
                       reason: a control validated by the instrument it controls
                       is circular, and that cost two sittings.

WHAT 25 TRIALS BUYS, written before the sitting. Widest at 0.5, 25 trials give
+/-19.6 points; a one-sided binomial rejects chance from 17/25 (68.0%). So this
resolves "can he hear it in two trials out of three" and CANNOT resolve a 60%
tell from 50%. That is deliberate. This is a gate, whose job is to stop an
expensive route that is obviously broken, not an equivalence proof — 0039 records
that equivalence needs ~200 trials. A pass means "not obviously broken, proceed",
never "transparent".

PRE-REGISTERED READING.

  anchor at or near chance ................. sitting VOID, fix the page
  cont32 audible ........................... route dead, stop
  every noise arm at chance incl. 0.80 ..... NO POWER, not a pass. The page
                                             cannot see latent noise at all;
                                             believe nothing else on it.
  cont32 + .20 at chance, .80 audible ...... the intended pass. Budget is real
                                             and lies between, and the listener
                                             demonstrably can hear latent error.
  .20 audible .............................. budget is tight; a flow model must
                                             hold under 20% per-channel error.
                                             Proceed, but the model is now the
                                             risk rather than the representation.

RUN IT AS
    python run.py --bench      the offline ladder only, no listener, ~2 minutes
    python run.py              build the page for a sitting
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import librosa
import numpy as np
import torch
from scipy.signal import butter, sosfilt

import dac
from crowgpt.codec import Codec, normalise
from crowgpt.demo import ABXPage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
PAGE = HERE / "results" / "abx-continuous-latent.html"
SESSIONS = HERE / "results" / "listening"
SPECIES = "american-crow"
MIN_SECONDS = 1.0
SR = 24000
BENCH_ONLY = "--bench" in sys.argv

# 32 stages x 8 dims = the full 256-d latent. The bench below is what chose 32
# over 24, and it also chose this representation over the raw 1024-d encoder
# output, which decodes WORSE despite carrying strictly more information.
N_STAGES = 32
# THE BENCH CHOSE THESE, and it moved them. The first draft tested 10% and 20%
# error. Both land closer to raw (0.315, 0.425) than DAC-24 quantized (0.369),
# which 0039 proved ABX-transparent — so both were near-certain passes and would
# have spent 60 trials confirming a foregone conclusion. The arms now bracket the
# knee instead: 20% as the realistic case, 40% where the offline number matches
# EnCodec-6k (0.698 vs 0.739, also ABX-chance in 0039), 80% where it is finally
# clear of every codec ever measured here.
ARMS = (("cont32", 25), ("cont32+noise0.20", 25), ("cont32+noise0.40", 25),
        ("cont32+noise0.80", 25), ("lowpass_2k", 20))
SOS = butter(8, 2000, "lowpass", fs=SR, output="sos")


class Latent:
    """DAC's continuous cascade, with the codebook lookup taken out.

    THE CODEBOOK IS THE ONLY THING REMOVED. Each RVQ stage projects the running
    residual to 8 dimensions (`in_proj`), snaps that to a codebook entry, projects
    back to 1024 (`out_proj`) and subtracts. Dropping the snap leaves a rank-8
    linear cascade whose output is a rank-8N approximation of the encoder's z,
    and whose per-stage 8-vectors concatenate into exactly the tensor DAC itself
    calls `latents`.

    `quantizer.from_latents` LOOKS LIKE THIS AND IS NOT. Its docstring says
    "given the unquantized latents" and it then calls `decode_latents`, which is
    a nearest-neighbour codebook search. Anything routed through it is quantized
    and would have measured the discrete path under a continuous name.
    """

    def __init__(self, device="cuda", n_stages=N_STAGES):
        self.model = dac.DAC.load(dac.utils.download(model_type="24khz")).to(device).eval()
        self.quantizers = self.model.quantizer.quantizers[:n_stages]
        self.n_stages = n_stages
        self.device = device

    def z(self, samples):
        x = torch.from_numpy(np.asarray(samples, dtype=np.float32))[None, None].to(self.device)
        with torch.no_grad():
            return self.model.encoder(self.model.preprocess(x, SR))

    def encode(self, samples):
        """samples -> [1, 8*n_stages, frames] continuous latent."""
        residual, parts = self.z(samples), []
        with torch.no_grad():
            for q in self.quantizers:
                projected = q.in_proj(residual)
                parts.append(projected)
                residual = residual - q.out_proj(projected)
        return torch.cat(parts, dim=1)

    def decode(self, latent):
        summed = 0.0
        with torch.no_grad():
            for i, q in enumerate(self.quantizers):
                summed = summed + q.out_proj(latent[:, i * 8 : (i + 1) * 8, :])
            audio = self.model.decode(summed)
        return audio.squeeze(1).squeeze(0).cpu().numpy()

    def quantized(self, samples, n):
        with torch.no_grad():
            z_q, _, _, _, _ = self.model.quantizer(self.z(samples), n_quantizers=n)
            return self.model.decode(z_q).squeeze(1).squeeze(0).cpu().numpy()

    def raw_z(self, samples):
        with torch.no_grad():
            return self.model.decode(self.z(samples)).squeeze(1).squeeze(0).cpu().numpy()


def log_mel_distance(a, b):
    """Mean absolute log-mel difference. Ranks; does not transfer.

    0039 quotes DAC-24 at 0.617 and a 2 kHz lowpass at 5.522 on "log-mel
    distance" but the implementation is not in the repo, and this one does not
    reproduce those absolutes — it puts EnCodec-6k at 0.739 against 0039's 0.716
    (close) and DAC-24 at 0.369 against 0.617 (not). So the anchors here are for
    ORDERING arms within this file only. The audible/inaudible boundary is
    settled by the sitting, never by this number.
    """
    n = min(len(a), len(b))
    mel = lambda x: np.log(librosa.feature.melspectrogram(
        y=np.asarray(x[:n], dtype=np.float64), sr=SR,
        n_fft=1024, hop_length=256, n_mels=80) + 1e-7)
    A, B = mel(a), mel(b)
    w = min(A.shape[1], B.shape[1])
    return float(np.mean(np.abs(A[:, :w] - B[:, :w])))


def heard_bouts():
    """Bouts actually played to Ben, from the saved sessions."""
    used = set()
    for path in SESSIONS.glob("*/session-*.json"):
        try:
            session = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        for trial in session.get("trials", []):
            if trial.get("bout") is not None:
                used.add(int(trial["bout"]))
    return used


def previous_page():
    path = OUT / "trials.json"
    if not path.exists():
        return None
    return [int(t["bout"]) for t in json.loads(path.read_text())]


def choose_pool(store, need):
    """Held-out American Crow, one bout per recording, never heard.

    A REBUILD MUST NOT COST BOUTS — 0039's rule, learned by burning 360 unheard
    bouts on three rebuilds chasing a JavaScript bug. A page whose bouts appear in
    no saved session was never sat and is reissued exactly as it was. A page that
    was even partly sat is retired whole, because the post-answer reveal names
    the arm.
    """
    heard = heard_bouts()
    previous = previous_page()
    if previous and not (set(previous) & heard):
        return previous, "reissued unchanged — the last build was never sat"

    retire = heard | set(previous or ())
    seen, pool = set(), []
    for i in store.split(seed=0)["test"]:
        row = store.index[i]
        if row["species"] != SPECIES or i in retire:
            continue
        if row["recording_id"] in seen or row["n_samples"] / SR < MIN_SECONDS:
            continue
        seen.add(row["recording_id"])
        pool.append(i)
    if len(pool) < need:
        raise SystemExit(
            f"only {len(pool)} unheard bouts over {MIN_SECONDS}s remain; need {need}. "
            f"Lower the trial counts rather than reusing bouts."
        )
    return pool[:need], f"{len(pool)} available, {len(retire)} retired"


def channel_scale(latent, store, picks):
    """Per-channel standard deviation over the pool, as the unit of model error.

    GLOBAL, NOT PER BOUT. A model's error is a fixed magnitude in latent space;
    scaling noise by each clip's own spread would make quiet bouts get quiet
    error and hide exactly the case where error is loudest relative to signal.
    """
    total, count = 0.0, 0
    for i in picks:
        values = latent.encode(normalise(store.audio(store.index[i])))
        total = total + (values ** 2).sum(dim=(0, 2))
        count += values.shape[-1]
    return torch.sqrt(total / count)[None, :, None]


def treat(name, samples, latent, scale, generator):
    if name == "lowpass_2k":
        return sosfilt(SOS, samples).astype(np.float32)
    values = latent.encode(samples)
    if name.startswith("cont") and "+noise" in name:
        sigma = float(name.split("+noise")[1])
        values = values + torch.randn(values.shape, generator=generator,
                                      device=values.device) * scale * sigma
    return latent.decode(values)


def bench(latent, store, picks):
    """The offline ladder that chose the representation. Ranking only."""
    encodec = Codec(bandwidth=6.0)
    rows = {}
    for i in picks:
        raw = normalise(store.audio(store.index[i]))
        arms = {
            "lowpass_2k": sosfilt(SOS, raw).astype(np.float32),
            "encodec_6kbps": np.asarray(encodec.roundtrip(raw)[0], dtype=np.float32),
            "dac_quantized_24cb": latent.quantized(raw, 24),
            "dac_quantized_32cb": latent.quantized(raw, 32),
            "dac_raw_z_no_quantizer": latent.raw_z(raw),
        }
        values = latent.encode(raw)
        arms["cont32"] = latent.decode(values)
        deviation = values.std(dim=(0, 2), keepdim=True)
        for sigma in (0.05, 0.10, 0.20, 0.40, 0.80):
            noisy = values + torch.randn_like(values) * deviation * sigma
            arms[f"cont32+noise{sigma:.2f}"] = latent.decode(noisy)
        for key, audio in arms.items():
            rows.setdefault(key, []).append(
                log_mel_distance(raw, np.asarray(audio).ravel()))
    del encodec
    torch.cuda.empty_cache()
    return {k: round(float(np.mean(v)), 4) for k, v in rows.items()}


def main():
    stages = ["choose", "bench"] if BENCH_ONLY else ["choose", "bench", "render", "page"]
    run = Run("0052 — ARE CONTINUOUS LATENTS FORGIVING", stages)
    try:
        store = BoutStore(DATA / "bouts")
        latent = Latent()
        need = sum(count for _, count in ARMS)

        with run.stage("choose") as stage:
            pool, how = choose_pool(store, need)
            stage.say(f"{len(pool)} bouts — {how}")

        with run.stage("bench") as stage:
            table = bench(latent, store, pool[:40])
            stage.say(f"cont32 {table['cont32']} vs dac24 {table['dac_quantized_24cb']}")
            (OUT / "bench.json").write_text(json.dumps(table, indent=2) + "\n")
            for key in sorted(table, key=table.get):
                print(f"   {key:26s} {table[key]:7.4f}", flush=True)

        if BENCH_ONLY:
            run.note(f"bench only — cont32 {table['cont32']}")
            return

        generator = torch.Generator(device=latent.device).manual_seed(52)
        trials = []
        with run.stage("render") as stage:
            scale = channel_scale(latent, store, pool[:40])
            cursor = 0
            for name, count in ARMS:
                for position in pool[cursor:cursor + count]:
                    row = store.index[position]
                    samples = normalise(store.audio(row))
                    treated = treat(name, samples, latent, scale, generator)
                    # A frame of extra length makes the trial answerable by clock.
                    treated = np.asarray(treated).ravel()[: samples.size]
                    trials.append({
                        "reference": samples,
                        "treated": normalise(treated),
                        "sr": SR,
                        "arm": name,
                        "bout": int(position),
                        "recording": row["recording_id"],
                        "seconds": round(row["n_samples"] / SR, 2),
                    })
                    stage.update(len(trials), need, extra=name)
                cursor += count

        with run.stage("page") as stage:
            page = ABXPage(
                trials,
                {
                    "Question": "is a continuous latent forgiving of error a code index is not",
                    "Arms": "cont32 (25) · +20% (25) · +40% (25) · +80% (25) · 2 kHz lowpass (20, anchor)",
                    "Chance": "50% — X is a copy of A or of B",
                    "Resolves": "68% per latent arm (n=25) · 75% for the anchor (n=20)",
                    "Cannot resolve": "a 60% tell from 50% — that needs ~200 trials",
                    "Corpus": f"{SPECIES}, held-out test split, one bout per recording",
                    "Never heard before": "every bout is new to this sitting",
                    "Void if": "the 2 kHz anchor does not come out well above chance",
                },
                seed=52,
                title="Which one is X?",
                balance_by="arm",
            )
            PAGE.parent.mkdir(parents=True, exist_ok=True)
            page.write(PAGE)
            (OUT / "trials.json").write_text(json.dumps(
                [{k: v for k, v in t.items() if k not in ("reference", "treated")}
                 for t in trials], indent=2) + "\n")
            stage.say(f"{len(trials)} trials -> {PAGE}")

        run.note(f"{len(trials)} ABX trials -> {PAGE}")
        print(f"\n   open {PAGE}", flush=True)
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
