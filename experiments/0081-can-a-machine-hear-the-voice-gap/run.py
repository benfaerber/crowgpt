"""0081: two off-the-shelf judges against the voice-0078 pool clips, CPU only."""
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

import numpy as np
import soundfile as sf

from crowgpt.embed import AstEmbedder, _to_rate
from crowgpt.metrics import frechet_distance
from crowgpt.progress import Run

OUT = Path(__file__).resolve().parent
POOL = HERE / "results" / "listening-pools" / "voice-0078"
SAMPLE_RATE = 24_000

CROW_PROMPTS = ["a crow cawing", "a raven calling"]
DEFECT_PROMPTS = ["a person screaming", "a frog croaking",
                  "a metallic robotic sound", "an alien sound effect"]


def load(path):
    audio, sr = sf.read(path, dtype="float32")
    assert sr == SAMPLE_RATE, (path, sr)
    return audio


def groups():
    out = defaultdict(list)
    for wav in sorted(POOL.glob("*.wav")):
        stem = wav.stem
        if stem.startswith(("anchor-", "real-")):
            out["real"].append(wav)
        elif stem.startswith(("calltype-", "catch-calltype-")):
            out["calltype"].append(wav)
        elif stem.startswith(("b32-", "catch-b32-")):
            out["b32"].append(wav)
    return out


def call_type_of(stem):
    for slug in ("alarm-call", "begging", "call", "song"):
        if f"-{slug}-" in stem or stem.endswith(slug):
            return slug
    return None


def main():
    run = Run("0081 — MACHINE JUDGES VS THE POOL", ["ast-fad", "clap"])
    report = {}
    grouped = groups()
    counts = {k: len(v) for k, v in grouped.items()}
    assert counts["real"] and counts["calltype"] and counts["b32"], counts
    report["clips"] = counts

    with run.stage("ast-fad") as stage:
        embedder = AstEmbedder(device="cpu")
        emb = {}
        done, total = 0, sum(counts.values())
        for name, wavs in grouped.items():
            vectors = []
            for wav in wavs:
                vectors.append(embedder.embed([load(wav)], SAMPLE_RATE)[0])
                done += 1
                stage.update(done, total, extra=name)
            emb[name] = np.stack(vectors)
        half = len(emb["real"]) // 2
        report["ast_fad"] = {
            "floor_real_vs_real": round(float(frechet_distance(
                emb["real"][:half], emb["real"][half:])), 3),
            "calltype_vs_real": round(float(frechet_distance(
                emb["real"], emb["calltype"])), 3),
            "b32_vs_real": round(float(frechet_distance(
                emb["real"], emb["b32"])), 3),
        }
        run.note(f"FAD: {report['ast_fad']}")

    with run.stage("clap") as stage:
        import torch
        from transformers import ClapModel, ClapProcessor

        model_id = "laion/clap-htsat-unfused"
        processor = ClapProcessor.from_pretrained(model_id)
        model = ClapModel.from_pretrained(model_id).eval()
        prompts = CROW_PROMPTS + DEFECT_PROMPTS
        def as_tensor(out):
            if isinstance(out, torch.Tensor):
                return out
            for key in ("text_embeds", "audio_embeds", "pooler_output"):
                value = getattr(out, key, None)
                if value is not None:
                    return value
            raise TypeError(f"no embedding tensor on {type(out).__name__}")

        with torch.no_grad():
            text = as_tensor(model.get_text_features(**processor(
                text=prompts, return_tensors="pt", padding=True)))
            text = torch.nn.functional.normalize(text, dim=-1)

        per_clip = []
        done, total = 0, sum(counts.values())
        for name, wavs in grouped.items():
            for wav in wavs:
                audio = _to_rate(load(wav), SAMPLE_RATE, 48_000)
                with torch.no_grad():
                    inputs = processor(audio=[audio], sampling_rate=48_000,
                                       return_tensors="pt")
                    vec = as_tensor(model.get_audio_features(**inputs))
                    vec = torch.nn.functional.normalize(vec, dim=-1)
                sims = (vec @ text.T)[0].tolist()
                row = {"group": name, "clip": wav.name,
                       "call_type": call_type_of(wav.stem),
                       **{p: round(s, 4) for p, s in zip(prompts, sims)}}
                row["margin"] = round(
                    float(np.mean(sims[: len(CROW_PROMPTS)])
                          - np.mean(sims[len(CROW_PROMPTS):])), 4)
                per_clip.append(row)
                done += 1
                stage.update(done, total, extra=name)

        summary = {}
        for name in grouped:
            rows = [r for r in per_clip if r["group"] == name]
            summary[name] = {
                "n": len(rows),
                "margin_mean": round(float(np.mean(
                    [r["margin"] for r in rows])), 4),
                **{p: round(float(np.mean([r[p] for r in rows])), 4)
                   for p in prompts},
            }
        by_type = {}
        for slug in ("alarm-call", "begging", "call", "song"):
            by_type[slug] = {
                name: round(float(np.mean(
                    [r["margin"] for r in per_clip
                     if r["group"] == name and r["call_type"] == slug])), 4)
                for name in ("calltype", "b32")}
        report["clap"] = {"summary": summary, "margin_by_type": by_type}
        (OUT / "clap_per_clip.json").write_text(
            json.dumps(per_clip, indent=2) + "\n")
        run.note(f"CLAP margins: "
                 f"{ {k: v['margin_mean'] for k, v in summary.items()} }")

    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
