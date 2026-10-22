"""Run the ABX page's JavaScript and click its buttons.

EVERY OTHER TEST IN test_abx.py PASSED ON A PAGE WITH DEAD BUTTONS. They check
what Python builds — the trial structure, the balance, the placeholders — and
the two faults that reached Ben were both in the browser: 360 retained media
elements that exhausted the page at trial 72, then a seek issued before the
media had loaded, which threw InvalidStateError and killed the click handler
outright. Ben's console said "the fetching process for the media resource was
aborted"; the page said nothing at all.

So this executes the real script from the real rendered page under a DOM stub
whose media element is as strict as a browser's: src assignment starts an
asynchronous load, seeking before readiness throws, and play() during a pending
load rejects. Then it clicks.

Skipped when node is absent rather than failing — it is a real dependency and
not everyone running the suite has it.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from crowgpt.demo import ABXPage

HARNESS = Path(__file__).parent / "dom_harness.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _tone(freq, seconds=0.3, sr=24000):
    t = np.arange(int(seconds * sr)) / sr
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def _script(page_html):
    body = re.search(r"<script>\n(.*)</script>", page_html, re.S).group(1)
    # Real audio payloads are megabytes; the logic under test does not read them.
    body = re.sub(r'"data:audio/wav;base64,[^"]*"', '"data:audio/wav;base64,STUB"', body)
    return body


def _run(page_html, driver):
    with __import__("tempfile").TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "page.js").write_text(_script(page_html))
        (tmp / "harness.js").write_text(HARNESS.read_text())
        (tmp / "main.js").write_text(
            "require('./harness.js');\n"
            "try { require('./page.js'); }\n"
            "catch (e) { console.log(JSON.stringify({load_error: e.message})); process.exit(0); }\n"
            + driver
        )
        out = subprocess.run(["node", "main.js"], cwd=tmp, capture_output=True, text=True,
                             timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture
def page():
    trials = [
        {"reference": _tone(400 + 40 * i),
         "treated": _tone(400 + 40 * i) + 0.3 * _tone(1800 + 40 * i),
         "arm": "big" if i < 6 else "small", "bout": i, "sr": 24000}
        for i in range(8)
    ]
    return ABXPage(trials, {"Question": "probe"}, seed=1, balance_by="arm").render()


DRIVER_CLICK = """
const rows = document.getElementById('trials').children;
const players = rows[0].children[1];
let threw = null;
try { players.children[0].click(); } catch (e) { threw = e.message; }
setTimeout(() => {
  console.log(JSON.stringify({rows: rows.length, buttons: players.children.length,
                              threw, played: PLAYED.length, errors: ERRORS}));
}, 30);
"""


def test_the_script_loads_at_all(page):
    result = _run(page, "console.log(JSON.stringify({ok: true}));")
    assert "load_error" not in result, result.get("load_error")


def test_clicking_play_actually_plays(page):
    """The regression. This failed on the shipped page with the real message."""
    result = _run(page, DRIVER_CLICK)
    assert result["threw"] is None, f"click handler threw: {result['threw']}"
    assert result["played"] == 1, "no audio was played"
    assert result["errors"] == [], result["errors"]


def test_every_trial_has_three_players_and_two_answers(page):
    driver = """
    const rows = document.getElementById('trials').children;
    const shape = [...rows].map(r => [r.children[1].children.length,
                                      r.children[2].children.length]);
    console.log(JSON.stringify({shape}));
    """
    assert all(p == [3, 2] for p in _run(page, driver)["shape"])


def test_answering_records_a_trial(page):
    driver = """
    const rows = document.getElementById('trials').children;
    rows[0].children[1].children[2].click();          // play X
    setTimeout(() => {
      let threw = null;
      try { rows[0].children[2].children[0].click(); } catch (e) { threw = e.message; }
      console.log(JSON.stringify({threw, done: document.getElementById('done').textContent}));
    }, 30);
    """
    result = _run(page, driver)
    assert result["threw"] is None, result["threw"]
    assert result["done"].startswith("1 /")


def test_only_one_media_element_is_constructed(page):
    """360 retained elements is what killed the first sitting at trial 72.

    Counted on the script with comments stripped — the fix's own comment quotes
    the construction it replaced, and matching that made this fail on a correct
    page.
    """
    script = re.sub(r"/\*.*?\*/", "", _script(page), flags=re.S)
    script = re.sub(r"^\s*//.*$", "", script, flags=re.M)
    assert script.count("new Audio") == 1


def test_play_happens_inside_the_user_gesture(page):
    """A browser refuses play() once the click's synchronous turn has ended.

    This is the second mute page: deferring play to a `canplay` handler avoids
    the InvalidStateError and gets NotAllowedError instead — aria-pressed flips,
    the handler completes, the promise rejects into a .catch, and there is no
    sound and nothing in the console.
    """
    result = _run(page, DRIVER_CLICK)
    assert "NotAllowedError" not in " ".join(result["errors"]), result["errors"]
    assert result["played"] == 1


def test_page_declares_its_encoding(page):
    """Over file:// there is no Content-Type, so an undeclared page gets
    guessed at — Firefox picked Latin-1 and rendered every em dash as "â€”"."""
    assert '<meta charset="utf-8">' in page
