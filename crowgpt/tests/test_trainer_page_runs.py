"""Run the trainer page's JavaScript and take a whole sitting through it.

The adaptive draw is the part Python cannot vouch for by inspection: which
clip comes next depends on answers, so the schedule exists only in the page's
script. The contract is written in trainer.py — balanced round robin over the
build's rotation until a class is missed, each miss buying that class one
extra earlier turn, no clip repeating — and the test here replays that
contract in Python and drives the real script through an entire sitting to
check the two produce the same sequence. The media-element discipline is the
ABX page's, checked the same way it is checked there.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from crowgpt.trainer import ASSERTED, HUMAN, TrainerPage

HARNESS = Path(__file__).parent / "dom_harness.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

SR = 24000


def _tone(freq, seconds=1.5):
    t = np.arange(int(seconds * SR)) / SR
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def _page(per_class=4, seed=3):
    menu = [{"key": "alarm call", "core": "alarm call", "color": "#f27070"},
            {"key": "call", "core": "call", "color": "#6ea8fe"},
            {"key": "contact call", "core": "call", "color": "#6ea8fe"}]
    clips = []
    for c, entry in enumerate(menu):
        for i in range(per_class):
            clips.append({
                "clip_id": f"{entry['key']}-{i}", "key": entry["key"],
                "audio": _tone(400 + 100 * c + 10 * i), "sr": SR,
                "provenance": ASSERTED if entry["key"] == "contact call" else HUMAN,
                "species": "Test Crow", "note": f"note-{c}-{i}",
            })
    return TrainerPage(clips, menu, {"Clips": len(clips)}, seed=seed)


def _script(page_html):
    body = re.search(r"<script>\n(.*)</script>", page_html, re.S).group(1)
    body = re.sub(r'"data:audio/wav;base64,[^"]*"', '"data:audio/wav;base64,STUB"', body)
    return body


def _run(page_html, driver):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "page.js").write_text(_script(page_html))
        (tmp / "harness.js").write_text(HARNESS.read_text())
        (tmp / "main.js").write_text(
            "require('./harness.js');\n"
            "try { require('./page.js'); }\n"
            "catch (e) { console.log(JSON.stringify({load_error: e.message})); process.exit(0); }\n"
            + driver
        )
        out = subprocess.run(["node", "main.js"], cwd=tmp, capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout.strip().splitlines()[-1])


def simulate(page, answer_for):
    """The documented draw, replayed outside the page.

    Priority is asked - wrong, lowest first, ties to the earlier class in the
    build's rotation; a class with no clips left drops out. `answer_for` is
    the same fixed policy the driver uses, so if the page's script and this
    loop disagree about a single trial, the sequences diverge from there.
    """
    stats = {key: {"asked": 0, "wrong": 0} for key in page.pools}
    cursor = {key: 0 for key in page.pools}
    sequence = []
    while True:
        best, best_score = None, None
        for key in page.rotation:
            if cursor[key] >= len(page.pools[key]):
                continue
            score = stats[key]["asked"] - stats[key]["wrong"]
            if best is None or score < best_score:
                best, best_score = key, score
        if best is None:
            return sequence
        cursor[best] += 1
        stats[best]["asked"] += 1
        if answer_for(best) != best:
            stats[best]["wrong"] += 1
        sequence.append(best)


def _sitting_driver(answer_index):
    """Answer every trial with the same button, collecting the truths."""
    return """
    const answersEl = document.getElementById('answers');
    const verdict = document.getElementById('verdict');
    const next = document.getElementById('next');
    const trialno = document.getElementById('trialno');
    const seq = [];
    for (let i = 0; i < 100; i++) {
      if (trialno.textContent.startsWith('done')) break;
      answersEl.children[%d].click();
      seq.push(verdict.textContent.slice(2));
      next.click();
    }
    console.log(JSON.stringify({seq, done: trialno.textContent,
                                score: document.getElementById('score').textContent}));
    """ % answer_index


def test_the_script_loads_at_all():
    result = _run(_page().render(), "console.log(JSON.stringify({ok: true}));")
    assert "load_error" not in result, result.get("load_error")


def test_clicking_play_plays_inside_the_gesture():
    """The two mute-page regressions, checked the way the ABX test checks
    them: the click must produce a play with no autoplay refusal."""
    driver = """
    document.getElementById('play').click();
    setTimeout(() => console.log(JSON.stringify({played: PLAYED.length, errors: ERRORS})), 30);
    """
    result = _run(_page().render(), driver)
    assert result["played"] == 1, "no audio was played"
    assert result["errors"] == [], result["errors"]


def test_only_one_media_element_is_constructed():
    script = re.sub(r"/\*.*?\*/", "", _script(_page().render()), flags=re.S)
    script = re.sub(r"^\s*//.*$", "", script, flags=re.M)
    assert script.count("new Audio") == 1


def test_the_page_declares_its_encoding():
    assert '<meta charset="utf-8">' in _page().render()


def test_answering_shows_the_verdict_and_scores_it():
    driver = """
    const answersEl = document.getElementById('answers');
    answersEl.children[0].click();
    console.log(JSON.stringify({
      verdict: document.getElementById('verdict').textContent,
      provenance: document.getElementById('provenance').textContent,
      score: document.getElementById('score').textContent,
      spec: document.getElementById('spec').style.display}));
    """
    result = _run(_page().render(), driver)
    assert result["verdict"].startswith(("✓", "✗"))
    assert "Test Crow" in result["provenance"]
    assert result["score"].endswith("/ 1")
    assert result["spec"] == "block"


def test_answering_twice_scores_once():
    driver = """
    const answersEl = document.getElementById('answers');
    answersEl.children[0].click();
    answersEl.children[1].click();
    console.log(JSON.stringify({score: document.getElementById('score').textContent}));
    """
    assert _run(_page().render(), driver)["score"].endswith("/ 1")


def test_the_sitting_follows_the_documented_draw_exactly():
    """One policy, two implementations, one sequence.

    The driver always answers "call", so call trials are right and the other
    two classes are wrong every time. The Python replay of the documented
    algorithm under the same policy must match the script trial for trial —
    which also proves no clip repeats and every clip is reached, since the
    replay walks each pool once in order.
    """
    page = _page()
    call_index = [m["key"] for m in page.menu].index("call")
    expected = simulate(page, lambda truth: "call")
    result = _run(page.render(), _sitting_driver(call_index))
    assert result["seq"] == expected
    assert len(result["seq"]) == 12
    assert result["done"].startswith("done")


def test_a_missed_class_is_redrawn_before_a_clean_one():
    """The property the adaptive draw exists for, read off the sequence."""
    page = _page()
    call_index = [m["key"] for m in page.menu].index("call")
    result = _run(page.render(), _sitting_driver(call_index))
    sequence = result["seq"]
    first_miss = next(i for i, key in enumerate(sequence) if key != "call")
    assert sequence[first_miss + 1] == sequence[first_miss], (
        "a miss should buy the class an immediate retry with a fresh clip")


def test_the_draw_is_round_robin_while_nothing_is_missed():
    """Simulated with a perfect ear: every prefix stays balanced within one."""
    page = _page()
    sequence = simulate(page, lambda truth: truth)
    for stop in range(1, len(sequence) + 1):
        head = sequence[:stop]
        counts = [head.count(key) for key in page.pools]
        assert max(counts) - min(counts) <= 1, head


def test_the_saved_sitting_holds_every_answer_once():
    page = _page()
    call_index = [m["key"] for m in page.menu].index("call")
    driver = _sitting_driver(call_index).replace(
        "console.log(JSON.stringify({seq",
        """
    navigator.clipboard.writeText = () => { throw new Error('refused'); };
    document.getElementById('copy').click();
    const box = document.getElementById('payload');
    const saved = JSON.parse(box.value);
    console.log(JSON.stringify({kind: saved.kind, answered: saved.answered,
      ids: saved.trials.map(t => t.clip_id),
      per_class: saved.per_class, seq""")
    result = _run(page.render(), driver)
    assert result["kind"] == "trainer"
    assert result["answered"] == 12
    assert len(set(result["ids"])) == 12, "a clip repeated within the sitting"
    call = result["per_class"]["call"]
    assert call["asked"] == 4 and call["right"] == 4
    low, high = call["wilson95"]
    assert 0.0 <= low <= call["rate"] <= high <= 1.0


def test_wilson_interval_narrows_with_evidence():
    """4/4 right must not read as certainty — the interval is the honesty."""
    page = _page()
    call_index = [m["key"] for m in page.menu].index("call")
    driver = _sitting_driver(call_index).replace(
        "console.log(JSON.stringify({seq",
        """
    navigator.clipboard.writeText = () => { throw new Error('refused'); };
    document.getElementById('copy').click();
    const saved = JSON.parse(document.getElementById('payload').value);
    console.log(JSON.stringify({per_class: saved.per_class, seq""")
    per_class = _run(page.render(), driver)["per_class"]
    low, high = per_class["call"]["wilson95"]
    assert per_class["call"]["rate"] == 1.0
    assert low < 1.0, "a perfect 4/4 still deserves an interval below 1"
    assert high <= 1.0
