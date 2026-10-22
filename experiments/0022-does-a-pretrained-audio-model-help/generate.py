"""Generate the base and LoRA arms from Stable Audio 3, same prompts, same seeds.

Runs in the stable-audio-3 venv, which has no BirdNET and no crowgpt in it. The
scoring lives in evaluate.py on the other side; this only writes wavs.

THE BASE ARM IS THE POINT, not a formality. Stable Audio was trained on a large
audio corpus and has certainly heard birds, so it may well produce something
crow-shaped from the prompt alone. Without that control a good LoRA result is
unattributable — we would be measuring what the phrase "American Crow alarm
call" already buys, and crediting it to 2,961 bouts. Same prompts and same seeds
in both arms, so the only difference is the adapter.

Sampler settings are taken from whatever the model's own UI would default to
rather than typed in here: a rectified-flow denoiser wants 8 steps at CFG 1.0
and the others want 50 at 7.0, and guessing the wrong pair makes a model look
broken when it is merely being driven wrong.
"""
import argparse
import json
from pathlib import Path

import torch

CORE = ("alarm call", "begging", "call", "song")
SCENE = "wild bird vocalization, outdoor field recording, natural ambience"
PHRASING = {
    "alarm call": "American Crow alarm call, harsh repeated cawing",
    "begging": "American Crow begging call, juvenile food-solicitation calls",
    "call": "American Crow call, single spaced caws",
    "song": "American Crow song, quiet varied warbling subsong",
}


def sampler_defaults(model):
    """What this model's own interface would use, rather than a guess."""
    diffusion = model.model_config.get("model", {}).get("diffusion", {})
    is_rf = "rf" in str(diffusion.get("type", "")).lower() or "rectified" in str(
        diffusion.get("diffusion_objective", "")
    ).lower()
    try:
        from stable_audio_3.interface.diffusion_cond import is_rf_denoiser as probe
        is_rf = bool(probe(model.model))
    except Exception:
        pass
    return (8, 1.0) if is_rf else (50, 7.0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="small-sfx-base")
    p.add_argument("--lora", default=None, help="LoRA .ckpt/.safetensors, omit for the base arm")
    p.add_argument("--out", required=True)
    p.add_argument("--per_type", type=int, default=30)
    p.add_argument("--duration", type=float, default=5.0)
    p.add_argument("--seed_base", type=int, default=7000)
    args = p.parse_args()

    from stable_audio_3 import StableAudioModel

    model = StableAudioModel.from_pretrained(args.model, model_half=False)
    if args.lora:
        # A LIST, always. load_lora takes a sequence because several adapters can
        # be stacked, so handing it a bare string iterates the characters and
        # tries to torch.load("/") — which fails as a confusing IsADirectoryError
        # rather than anything resembling "wrong argument type".
        model.load_lora([args.lora])
    steps, cfg = sampler_defaults(model)
    print(f"steps={steps} cfg={cfg} lora={args.lora}", flush=True)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    import soundfile as sf

    written = []
    for call_type in CORE:
        prompt = f"{PHRASING[call_type]}, {SCENE}"
        for i in range(args.per_type):
            audio = model.generate(prompt=prompt, duration=args.duration, steps=steps,
                                   cfg_scale=cfg, batch_size=1, seed=args.seed_base + i)
            wave = audio[0] if audio.dim() == 3 else audio
            wave = wave.float().cpu().numpy().T
            name = f"{call_type.replace(' ', '-')}-{i:03d}.wav"
            sf.write(str(out / name), wave, model.model.sample_rate, subtype="PCM_16")
            written.append({"file": name, "call_type": call_type, "seed": args.seed_base + i})
        print(f"  {call_type}: {args.per_type}", flush=True)

    (out / "index.json").write_text(json.dumps(
        {"arm": "lora" if args.lora else "base", "model": args.model,
         "lora": args.lora, "steps": steps, "cfg_scale": cfg,
         "duration": args.duration, "sample_rate": model.model.sample_rate,
         "clips": written}, indent=2) + "\n")
    print(f"wrote {len(written)} clips to {out}")


if __name__ == "__main__":
    main()
