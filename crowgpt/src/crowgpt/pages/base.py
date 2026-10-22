"""What every listening page shares: the clip rules, the encoders, the stylesheet.

One stylesheet for all of them, kept here so a page cannot drift from the
look of the listening test. It used to be sliced out of DemoPage's template
at import time; it is now the source, and demo_page.py composes its template
around it.
"""

import base64
import io
import numpy as np
import soundfile as sf


DEMO_SR = 16000
PEAKS = 160

# A clip shorter than this cannot be graded and its trial is decided before the
# listener has heard anything about timbre.
#
# 0044 IS WHY THIS IS ENFORCED HERE RATHER THAN LEFT TO EACH EXPERIMENT.
# PLAN-TIMBRE recorded the rule after finding it live — "clips under 1 second
# are ungradeable; filtering them took a raw control from 0.87 to 0.96, so
# filter at build time, not after" — and every experiment that then implemented
# it (0028, 0033, 0034, 0037, 0038, 0041, and 0044's first build) applied it to
# `store.index[i]["n_samples"]`, the REAL bout store, and to nothing else.
# Generated arms went in unfiltered at 18-20% under a second, shortest 0.08 s.
#
# That is a one-sided bias rather than noise: the real arm was filtered and the
# generated arm was not. Ben, mid-sitting: "too short clips instantly loose. 0.1
# second is always worse." Removing them changed his description of the defect
# from "background beeps" and "modem" to "hoarse crow" and "scratchy".
#
# So the check lives with the pages, which is the one place every sitting passes
# through. It raises rather than silently dropping, because a page that quietly
# discards clips changes an arm's n without saying so.
MIN_GRADEABLE_SECONDS = 1.0


def _check_gradeable(clips, where):
    """Refuse a page carrying clips too short to judge.

    `clips` is an iterable of (samples, sample_rate). Raising is deliberate: the
    caller has to decide whether to over-draw or to lower the bar, and both are
    choices worth making explicitly in the experiment rather than here.
    """
    short = [len(np.asarray(samples)) / sr for samples, sr in clips
             if sr and len(np.asarray(samples)) / sr < MIN_GRADEABLE_SECONDS]
    if short:
        shortest = min(short)
        raise ValueError(
            f"{where}: {len(short)} clip(s) under {MIN_GRADEABLE_SECONDS}s "
            f"(shortest {shortest:.2f}s). Short clips are ungradeable and lose "
            f"on sight — 0044. Filter at build time and over-draw to hold n, or "
            f"pass min_seconds=0 if this page genuinely does not need it."
        )


def _wav_data_uri(samples, sr, target_sr=DEMO_SR):
    """`target_sr=None` keeps the native rate.

    THE DEFAULT THROWS AWAY EVERYTHING ABOVE 8 kHz, which is fine for the pages
    that ask "does this sound like a crow" and wrong for one that asks "are
    these two identical". 0036 measured both codecs altering the >6 kHz band —
    EnCodec by −0.66 dB and DAC by −1.42 dB in call regions — and a 16 kHz
    render deletes the upper half of that before the listener hears it. A
    transparency test must not discard the evidence it is looking for.
    """
    from scipy.signal import resample_poly

    samples = np.asarray(samples, dtype=np.float32)
    rate = int(sr) if target_sr is None else int(target_sr)
    if sr != rate:
        from math import gcd

        divisor = gcd(int(sr), rate)
        samples = resample_poly(samples, rate // divisor, int(sr) // divisor)
    peak = float(np.max(np.abs(samples))) or 1.0
    samples = np.clip(samples / peak * 0.95, -1.0, 1.0)

    buffer = io.BytesIO()
    sf.write(buffer, samples, rate, format="WAV", subtype="PCM_16")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:audio/wav;base64,{encoded}", samples


def _peaks(samples, count=PEAKS):
    if samples.size == 0:
        return [0.0] * count
    chunks = np.array_split(np.abs(samples), count)
    values = np.array([float(c.max()) if c.size else 0.0 for c in chunks])
    ceiling = values.max() or 1.0
    return [round(float(v / ceiling), 3) for v in values]


_CSS = r"""<style>
  :root {
    --ground: #EDEFED;
    --raised: #FFFFFF;
    --line: #D3D8D4;
    --ink: #14181A;
    --soft: #5C6663;
    --accent: #6D4FD1;
    --accent-soft: #EFEAFB;
    --right: #1B7F53;
    --wrong: #B34733;
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground: #0F1214;
      --raised: #171B1E;
      --line: #2A3034;
      --ink: #E8EBE9;
      --soft: #939E9A;
      --accent: #A48CF0;
      --accent-soft: #241D3D;
      --right: #4FC48A;
      --wrong: #E08268;
    }
  }
  :root[data-theme="dark"] {
    --ground: #0F1214; --raised: #171B1E; --line: #2A3034; --ink: #E8EBE9;
    --soft: #939E9A; --accent: #A48CF0; --accent-soft: #241D3D;
    --right: #4FC48A; --wrong: #E08268;
  }
  :root[data-theme="light"] {
    --ground: #EDEFED; --raised: #FFFFFF; --line: #D3D8D4; --ink: #14181A;
    --soft: #5C6663; --accent: #6D4FD1; --accent-soft: #EFEAFB;
    --right: #1B7F53; --wrong: #B34733;
  }

  body { background: var(--ground); color: var(--ink); font-family: var(--serif);
         line-height: 1.6; margin: 0; }
  .wrap { max-width: 60rem; margin: 0 auto; padding: 3rem 1.25rem 5rem; }

  .eyebrow { font-family: var(--mono); font-size: .72rem; letter-spacing: .16em;
             text-transform: uppercase; color: var(--soft); margin: 0 0 .75rem; }
  h1 { font-family: var(--mono); font-size: clamp(1.9rem, 5vw, 3rem); font-weight: 600;
       letter-spacing: -.02em; line-height: 1.05; margin: 0 0 1rem; text-wrap: balance; }
  .lede { font-size: 1.08rem; max-width: 34em; color: var(--ink); margin: 0 0 .9rem; }
  .caveat { font-size: .95rem; max-width: 34em; color: var(--soft); margin: 0; }

  .score { position: sticky; top: 0; z-index: 5; margin: 2.5rem 0 1.5rem;
           background: var(--raised); border: 1px solid var(--line); border-radius: 2px;
           padding: .85rem 1.1rem; display: flex; gap: 1.75rem; align-items: baseline;
           flex-wrap: wrap; font-family: var(--mono); }
  .score b { font-size: 1.5rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .score span { font-size: .72rem; letter-spacing: .14em; text-transform: uppercase;
                color: var(--soft); display: block; }

  .trial { background: var(--raised); border: 1px solid var(--line); border-radius: 2px;
           padding: 1rem 1.1rem; margin-bottom: .6rem; display: grid;
           grid-template-columns: auto 1fr auto; gap: 1rem; align-items: center; }
  @media (max-width: 40rem) { .trial { grid-template-columns: auto 1fr; }
                              .controls { grid-column: 1 / -1; } }

  /* Play sits WITH the answer buttons, not across the row from them. Sixty
     trials is sixty round trips of the mouse if they are at opposite ends. */
  .controls { display: flex; align-items: center; gap: .6rem; }
  .trial.current { border-color: var(--accent); }
  .trial.current .idx { color: var(--accent); font-weight: 600; }
  .keyhint { font-family: var(--mono); font-size: .72rem; color: var(--soft);
             margin: .4rem 0 0; }

  .idx { font-family: var(--mono); font-size: .78rem; color: var(--soft);
         font-variant-numeric: tabular-nums; }
  .play { width: 2.6rem; height: 2.6rem; border-radius: 50%; border: 1px solid var(--line);
          background: transparent; color: var(--ink); cursor: pointer; font-size: .9rem;
          display: grid; place-items: center; }
  .play:hover { border-color: var(--accent); color: var(--accent); }
  .play[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
  .lead { display: flex; align-items: center; gap: .75rem; }
  canvas { width: 100%; height: 46px; display: block; }

  .recorder { margin-top: 2.5rem; border-top: 1px solid var(--line); padding-top: 1.5rem; }
  .recorder h2 { font-family: var(--mono); font-size: .78rem; letter-spacing: .16em;
                 text-transform: uppercase; color: var(--soft); font-weight: 600;
                 margin: 0 0 .8rem; }
  .recorder p { max-width: 34em; font-size: .9rem; color: var(--soft); }
  .recorder textarea { width: 100%; font-family: var(--mono); font-size: .78rem;
                       background: var(--raised); color: var(--ink);
                       border: 1px solid var(--line); border-radius: 2px;
                       padding: .6rem; margin: .6rem 0; }
  #note { height: 4.5rem; }
  #payload { height: 7rem; display: none; }
  .recorder .choices button { padding: .55rem 1rem; }
  #saved { font-family: var(--mono); font-size: .74rem; color: var(--right);
           margin-left: .6rem; }

  .choices { display: flex; gap: .4rem; }
  .choices button { font-family: var(--mono); font-size: .74rem; letter-spacing: .1em;
                    text-transform: uppercase; padding: .5rem .8rem; cursor: pointer;
                    background: transparent; color: var(--ink);
                    border: 1px solid var(--line); border-radius: 2px; }
  .choices button:hover { border-color: var(--accent); color: var(--accent); }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .verdict { font-family: var(--mono); font-size: .74rem; letter-spacing: .08em;
             text-transform: uppercase; white-space: nowrap; }
  .verdict.right { color: var(--right); }
  .verdict.wrong { color: var(--wrong); }
  .meta { font-family: var(--mono); font-size: .7rem; color: var(--soft);
          grid-column: 2 / -1; margin-top: -.35rem; }

  .method { margin-top: 3rem; border-top: 1px solid var(--line); padding-top: 1.5rem; }
  .method h2 { font-family: var(--mono); font-size: .78rem; letter-spacing: .16em;
               text-transform: uppercase; color: var(--soft); font-weight: 600; margin: 0 0 1rem; }
  .method p { max-width: 34em; font-size: .95rem; }
  .facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
           gap: 1px; background: var(--line); border: 1px solid var(--line);
           margin: 1.5rem 0; }
  .facts div { background: var(--raised); padding: .8rem .9rem; }
  .facts dt { font-family: var(--mono); font-size: .66rem; letter-spacing: .12em;
              text-transform: uppercase; color: var(--soft); margin-bottom: .3rem; }
  .facts dd { font-family: var(--mono); font-size: 1.1rem; margin: 0;
              font-variant-numeric: tabular-nums; }
</style>"""
