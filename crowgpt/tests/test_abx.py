"""ABXPage's failure mode is silent and it looks exactly like a positive result.

A page whose X is not really byte-identical to one side, or whose `truth` does
not match the audio it labels, still renders, still records a session and still
produces a number near 50% — which is the answer this instrument exists to
report. There is no way to notice from the page, so it is checked here.
"""

import json
import re

import numpy as np
import pytest

from crowgpt.demo import ABXPage, _wav_data_uri


def _tone(freq, seconds=0.4, sr=24000):
    t = np.arange(int(seconds * sr)) / sr
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


@pytest.fixture
def trials():
    # The treatment adds a partial rather than changing level: _wav_data_uri
    # peak-normalises, so a gain-only "difference" renders byte-identical and
    # is not a difference at all — see test_level_is_not_a_cue.
    return [
        {"reference": _tone(400 + 30 * i),
         "treated": _tone(400 + 30 * i) + 0.3 * _tone(1600 + 30 * i),
         "arm": "test", "bout": i}
        for i in range(24)
    ]


def test_x_is_not_carried_as_a_third_clip(trials):
    """X is a pointer to a side, so it cannot drift from the audio it claims."""
    for trial in ABXPage(trials, {}).trials:
        assert "x" not in trial
        assert trial["truth"] in ("a", "b")


def test_the_page_plays_the_side_x_points_at(trials):
    """The one line that makes the pointer real, asserted on the rendered JS."""
    assert 'role === "x" ? trial[trial.truth]' in ABXPage(trials, {}).render()


def test_the_two_sides_differ(trials):
    """If A and B render identically the trial is unanswerable, not hard."""
    for trial in ABXPage(trials, {}).trials:
        assert trial["a"] != trial["b"]


def test_identical_sides_are_rejected():
    """An untreated 'treated' arm scores 50%, which reads as transparent."""
    passthrough = [{"reference": _tone(500), "treated": _tone(500), "arm": "broken"}]
    with pytest.raises(ValueError, match="identically on both sides"):
        ABXPage(passthrough, {})


def test_level_is_not_a_cue():
    """Every clip is peak-normalised, so loudness cannot carry the answer.

    PLAN-TIMBRE's second protocol lesson, found live in an earlier sitting:
    peak-normalise every arm including raw, or level becomes the tell. Asserted
    on the renderer rather than through ABXPage's guard because the guard is
    byte equality — a gain that does not survive 16-bit quantisation exactly
    leaves sub-LSB noise, which is a different (and inaudible) thing.
    """
    loud, _ = _wav_data_uri(_tone(500), 24000)
    quiet, _ = _wav_data_uri(_tone(500) * 0.5, 24000)
    assert loud == quiet


def test_reference_side_swaps(trials):
    """Answering 'A' every time must score chance, so the raw side has to move."""
    sides = [t["reference_side"] for t in ABXPage(trials, {}).trials]
    assert set(sides) == {"a", "b"}
    assert 0.2 < sides.count("a") / len(sides) < 0.8


def test_reference_side_and_truth_are_independent(trials):
    """If X were always the treated clip, 'X is the odd one' would always win."""
    page = ABXPage(trials, {})
    agree = sum(t["truth"] == t["reference_side"] for t in page.trials)
    assert 0.2 < agree / len(page.trials) < 0.8


def test_truth_is_balanced(trials):
    truths = [t["truth"] for t in ABXPage(trials, {}).trials]
    assert 0.2 < truths.count("a") / len(truths) < 0.8


def test_no_waveform_is_exposed(trials):
    """Three drawn waveforms would let the answer be read off by eye."""
    page = ABXPage(trials, {})
    for trial in page.trials:
        assert "peaks" not in trial
    assert "peaks" not in page.render()


def test_hidden_metadata_is_carried_but_not_the_audio(trials):
    trial = ABXPage(trials, {}).trials[0]
    assert trial["hidden"]["arm"] == "test"
    assert "reference" not in trial["hidden"]
    assert "treated" not in trial["hidden"]


def test_render_substitutes_every_placeholder(trials):
    page = ABXPage(trials, {"corpus": "test"}, title="probe").render()
    assert "__TRIALS__" not in page
    assert "__FACTS__" not in page
    assert "__TITLE__" not in page
    assert "probe" in page


def test_trials_embed_as_valid_json(trials):
    """A render that produces broken JS fails only when Ben opens it."""
    page = ABXPage(trials, {}).render()
    payload = re.search(r"const TRIALS = (\[.*?\]);\n", page, re.S).group(1)
    assert len(json.loads(payload)) == len(trials)


def test_seed_is_deterministic(trials):
    a = [(t["truth"], t["reference_side"]) for t in ABXPage(trials, {}, seed=7).trials]
    b = [(t["truth"], t["reference_side"]) for t in ABXPage(trials, {}, seed=7).trials]
    assert a == b


def test_write_creates_the_file(trials, tmp_path):
    path = ABXPage(trials, {}).write(tmp_path / "deep" / "abx.html")
    assert path.exists() and path.stat().st_size > 1000


def _mixed_arms(n_big=90, n_small=30):
    return (
        [{"reference": _tone(300 + i), "treated": _tone(300 + i) + 0.3 * _tone(1500 + i),
          "arm": "big", "bout": i} for i in range(n_big)]
        + [{"reference": _tone(900 + i), "treated": _tone(900 + i) + 0.3 * _tone(2100 + i),
            "arm": "small", "bout": 1000 + i} for i in range(n_small)]
    )


@pytest.mark.parametrize("seed", range(12))
def test_a_fixed_answer_cannot_beat_chance_in_any_arm(seed):
    """The defect this exists for: independent flips gave one arm 18/30 on "b",
    so pressing B every time scored 0.600 — the exact significance threshold at
    n=30, on the control arm that certifies the sitting."""
    page = ABXPage(_mixed_arms(), {}, seed=seed, balance_by="arm")
    per_arm = {}
    for trial in page.trials:
        per_arm.setdefault(trial["hidden"]["arm"], []).append(trial["truth"])
    for arm, truths in per_arm.items():
        for side in ("a", "b"):
            best = truths.count(side) / len(truths)
            assert best <= 0.5 + 1 / len(truths), f"{arm}: always-{side} scores {best}"


@pytest.mark.parametrize("seed", range(12))
def test_reference_side_is_balanced_per_arm(seed):
    page = ABXPage(_mixed_arms(), {}, seed=seed, balance_by="arm")
    per_arm = {}
    for trial in page.trials:
        per_arm.setdefault(trial["hidden"]["arm"], []).append(trial["reference_side"])
    for arm, sides in per_arm.items():
        assert abs(sides.count("a") - sides.count("b")) <= 1, arm


def test_balance_by_none_still_balances_globally():
    page = ABXPage(_mixed_arms(), {}, seed=3)
    truths = [t["truth"] for t in page.trials]
    assert abs(truths.count("a") - truths.count("b")) <= 1


def test_odd_group_sizes_do_not_crash():
    trials = [{"reference": _tone(400 + i), "treated": _tone(400 + i) + 0.3 * _tone(1700 + i),
               "arm": "odd" if i % 3 else "other", "bout": i} for i in range(17)]
    page = ABXPage(trials, {}, balance_by="arm")
    assert len(page.trials) == 17


def test_abx_renders_at_the_native_rate():
    """16 kHz would delete everything above 8 kHz, where part of the codec
    artefact lives (0036: EnCodec −0.66 dB and DAC −1.42 dB above 6 kHz)."""
    import base64, io
    import soundfile as sf
    trials = [{"reference": _tone(500, sr=24000),
               "treated": _tone(500, sr=24000) + 0.3 * _tone(1900, sr=24000),
               "arm": "t", "sr": 24000}]
    trial = ABXPage(trials, {}).trials[0]
    _, sr = sf.read(io.BytesIO(base64.b64decode(trial["a"].split(",", 1)[1])), dtype="float32")
    assert sr == 24000


def test_every_page_template_declares_utf8():
    """All five pages, not just ABX — they all carry em dashes in the title."""
    from crowgpt import demo
    for name in ("_TEMPLATE", "_COMPARE_TEMPLATE", "_CALLTYPE_TEMPLATE",
                 "_RATING_TEMPLATE", "_ABX_TEMPLATE"):
        assert '<meta charset="utf-8">' in getattr(demo, name), name
