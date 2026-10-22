# Setup notes

The result is in `README.md`. This is the environment behind it — what it cost
to get `biodenoising` (Earth Species Project, arXiv 2410.03427) running, and
what was measured on the way, including one upstream bug that makes the
documented entry point return an untrained model.

## Upstream's advertised entry point does not load the weights

**`dns48(pretrained=True)` returns a randomly initialised network.** This is the
call behind `--dns48`, which is the only thing the README tells you to run.

`utils.py:175` reads, in full:

    def load_model_state_dict(model, state_dict):
        current_model_dict = model.state_dict()
        #new_state_dict={k:v for k,v in state_dict.items() if ...}
        model.load_state_dict(current_model_dict, strict=False)
        return model

It re-loads the model's own freshly-initialised state and never touches the
`state_dict` argument — the line that would have used it is commented out. The
75 MB checkpoint is downloaded and discarded.

Measured by `verify_load_bug.py`: two consecutive `dns48(pretrained=True)` calls
differ in **48 of 48 tensors**, and **0 of 48** match the checkpoint. It is
random init, freshly drawn each call.

This is silent. A random Demucs still emits plausible attenuated audio, so
nothing in the output announces it. Load through `deserialize_model(pkg['model'])`
instead, which is what upstream's own `--model_path` branch does and what
`denoise_lib.py` now does.

**Everything measured before this was found is void**, including a "32 dB peak
crush" that was an artefact of the untrained net. The corrected numbers are
below.

## Level staging IS a confound — gain-stage before the model

Corrected finding; the earlier note here said the opposite, on random weights.

`Demucs.forward` divides by `(floor + std)` with `floor=1e-3` and multiplies the
output by `std`. Capture 96 has std 0.00101 and peaks at -43.7 dBFS, so the
floor is the same magnitude as the signal and the model is under-driven.

With the real weights, across applied gain that is undone afterwards:

| gain | in peak dBFS | out/in rms | out/in peak |
|---|---|---|---|
| 0 dB | -43.7 | -22.6 dB | -13.6 dB |
| 12 dB | -31.7 | -17.9 dB | -6.1 dB |
| 24 dB | -19.7 | -16.7 dB | -7.4 dB |
| 33 dB | -10.7 | -16.5 dB | -7.0 dB |
| 40 dB | -3.7 | -16.4 dB | -6.9 dB |

Roughly 6 dB of rms and 7 dB of peak drift between raw and gain-staged,
plateauing by about 24 dB of gain. **The run must peak-normalise each capture
before the model and undo the identical gain after**, or it measures the
stability floor rather than the denoiser. 0001 measured ~27 dB of unused
headroom across this corpus, so every capture is in the affected range.

The corrected effect is also far gentler than the broken path suggested: about
16 dB off the rms and 7 dB off the peak, with the peak now falling *less* than
the rms — the opposite of transient-crushing.

## One checkpoint, and it is 16 kHz

`model-16kHz-dns48.th`, 18.9M parameters, `model.sample_rate == 16000`, and the
CLI's `--sample_rate` accepts only `16000`. Output is written at the model rate.
That is the same 8 kHz ceiling that made 0003 reject the crow-tools denoiser,
against a measured 26.7% of capture 69's call energy above 8 kHz.

## It is CPU-only here, on purpose

Built against a **CPU-only torch** (`torch==2.13.0+cpu`, `torch.version.cuda is
None`) in this folder's own `.venv`, so it cannot allocate on the GPU even by
accident. Run everything through:

    nice -n 19 env CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=8 .venv/bin/python ...

Do **not** install this into `crowgpt/.venv`. That is the venv the training
runs use, and crowgpt imports lazily — a dependency swapped mid-run surfaces
hours later when `generate` first imports it.

Cost on a 7950X: 14.5 s of audio denoised in 1.68 s wall, ~740 MB RSS. The four
mower captures total 76 s, so the whole denoise stage is ~10 s of CPU.

## Installation is not what the README says

`pip install biodenoising_inference` fails — the package is not on PyPI. Its
dependency list is also incomplete: `librosa`, `norbert`, `einops`, `julius` and
`hydra-core` all have to be added by hand.

The package `__init__` imports `live.py`, which imports `sounddevice` at module
scope and raises `OSError: PortAudio library not found`. `denoise_lib.py` stubs
`sounddevice` before import rather than installing a system library, since live
microphone denoising is not wanted here.

## Vendored, not forked, and not installed

Upstream was created 2024-09-12, last pushed 2024-10-07 — **no commits in 22
months, 8 stars, zero forks**. Nobody else is mirroring it, and the weights live
in a Google Cloud Storage bucket rather than a release asset, so they are the
part most likely to vanish and the only part that cannot be rewritten.

So both halves are held locally and nothing reaches the network at run time:

- **Code** — `vendor/`, cloned at commit `47ca6e3` with `.git` stripped, 300 KB.
  MIT (Copyright 2024 Earth Species Project), so redistribution is unencumbered.
  `denoise_lib.py` puts `vendor/` on `sys.path`; the pip package is uninstalled
  and the environment no longer depends on GitHub being up.
- **Weights** — `$DATA_DIR/models/biodenoising/model-16kHz-dns48.th`, 75 MB,
  sha256 `e1f0da9d…ce7bd24a`, verified on every load. CC-BY-NC 4.0, so it stays
  out of git and carries a non-commercial obligation. `data/` is gitignored, so
  the hash in `denoise_lib.py` is the durable record.

A fork was considered and rejected: it would have carried the packaging fixes,
which are worth a dozen lines of workaround, and could not have touched the
16 kHz ceiling, which is what actually decides adoption. Vendoring gets the
durability a fork was wanted for without an upstream to track. The load bug is
the strongest argument for owning this at all — it is exactly the class of
defect that a pinned dependency still hands you, silently.

Note `verify_load_bug.py` imports `vendor/`'s own `pretrained.py` on purpose:
it is a regression test against the upstream code as shipped, so it must keep
using the broken path.

## The two design rules the run was built on

Both were written before the run and both earned their place:

`band_snr` is a 99th-over-10th-percentile ratio, so a denoiser that gates the
quiet passages toward zero inflates it almost by construction — the same
mechanism that puts merged captures at infinity (FUTURE.txt). It did exactly
that: band SNR more than doubled on all four captures while three of the four
crows disappeared.

A resample-to-16k-and-back arm is mandatory or the model cannot be told from its
own bandwidth ceiling (the trap 0020 caught). That arm is what proved the 8 kHz
ceiling was *not* the cause — `band16` kept 4/4 detections.
