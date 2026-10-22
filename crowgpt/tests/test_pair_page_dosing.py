"""Dosing: the sitting arrives in blocks with a rest between, and the blocks
still add up to one measurement.

The failure modes here are all quiet. A dose window that shows the wrong
slice grades the same trials twice and never touches the rest; a lockout
that never gets written serves the whole sitting as one wall (the exact
thing the feature exists to prevent); and a page that loads mid-rest but
still shows trials makes the rest advisory. Every one of those renders a
page that looks right.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from crowgpt.demo import PairPage

HARNESS = Path(__file__).parent / "dom_harness.js"
SR = 24000


def _clip(arm, seed):
    rng = np.random.default_rng(seed)
    return {"audio": rng.normal(0, 0.1, SR).astype(np.float32), "sr": SR, "arm": arm}


@pytest.fixture
def pairs():
    return [{"a": _clip("v3", i), "b": _clip("v2", 100 + i)} for i in range(12)]


class TestRender:
    def test_dosing_is_off_by_default(self, pairs):
        html = PairPage(pairs, {}, seed=0).render()
        assert "const DOSE = 0;" in html

    def test_dose_and_rest_are_baked_in(self, pairs):
        html = PairPage(pairs, {}, seed=0, dose=5, rest_minutes=30).render()
        assert "const DOSE = 5;" in html
        assert "const REST_MS = 1800000;" in html

    def test_page_key_is_stable_across_rebuilds(self, pairs):
        key = re.compile(r'const PAGE_KEY = ("[0-9a-f]+");')
        one = key.search(PairPage(pairs, {}, seed=0, dose=5).render()).group(1)
        two = key.search(PairPage(pairs, {}, seed=0, dose=5).render()).group(1)
        assert one == two


needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")


def _script(page_html):
    body = re.search(r"<script>\n(.*)</script>", page_html, re.S).group(1)
    return re.sub(r'"data:audio/wav;base64,[^"]*"',
                  '"data:audio/wav;base64,STUB"', body)


def _run(page_html, driver, stored=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "page.js").write_text(_script(page_html))
        (tmp / "harness.js").write_text(HARNESS.read_text())
        (tmp / "main.js").write_text(
            "require('./harness.js');\n"
            "const STORE = " + json.dumps(stored or {}) + ";\n"
            "global.localStorage = {\n"
            "  getItem(k) { return k in STORE ? STORE[k] : null; },\n"
            "  setItem(k, v) { STORE[k] = v; },\n"
            "};\n"
            "try { require('./page.js'); }\n"
            "catch (e) { console.log(JSON.stringify({load_error: e.message})); process.exit(0); }\n"
            + driver
        )
        out = subprocess.run(["node", "main.js"], cwd=tmp, capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout.strip().splitlines()[-1])


def _key(page):
    return re.search(r'const PAGE_KEY = "([0-9a-f]+)"', page.render()).group(1)


def _visibility(key):
    # Page consts are module-scoped under require, so the key is inlined.
    return f"""
const rows = document.getElementById('trials').children
  .filter(r => r.className === 'pair');
console.log(JSON.stringify({{
  total: rows.length,
  visible: rows.filter(r => r.style.display !== 'none').length,
  stored: STORE['crowgpt.dose.{key}'] || null,
}}));
process.exit(0);  // the rest screen's countdown timer would hold node open
"""


def _answer_block(key):
    # The saved sitting is read back from pick()'s own autosave rather than
    # from payload(), which the driver cannot reach.
    return f"""
const rows = document.getElementById('trials').children
  .filter(r => r.className === 'pair');
for (const row of rows) {{
  if (row.style.display === 'none') continue;
  row.children[3].children[1].click();
}}
const state = JSON.parse(STORE['crowgpt.dose.{key}'] || '{{}}');
const saved = Object.keys(STORE).filter(k => k.startsWith('crowgpt.pairwise.'));
const sitting = JSON.parse(STORE[saved[0]]);
console.log(JSON.stringify({{
  answered: sitting.rated, block: sitting.block, blocks: sitting.blocks,
  next_block: state.block, rest_pending: (state.resumeAt || 0) > Date.now(),
}}));
process.exit(0);
"""


@needs_node
class TestDoseRuntime:
    def test_first_visit_shows_only_the_first_block(self, pairs):
        page = PairPage(pairs, {}, seed=0, dose=5)
        got = _run(page.render(), _visibility(_key(page)))
        assert got == {"total": 12, "visible": 5, "stored": None}

    def test_a_later_block_resumes_where_the_last_stopped(self, pairs):
        page = PairPage(pairs, {}, seed=0, dose=5)
        got = _run(page.render(), _visibility(_key(page)), stored={
            f"crowgpt.dose.{_key(page)}": json.dumps({"block": 2, "resumeAt": 0})})
        assert got["visible"] == 2  # trials 11..12, the tail block

    def test_mid_rest_the_page_serves_nothing(self, pairs):
        page = PairPage(pairs, {}, seed=0, dose=5)
        future = json.dumps({"block": 1, "resumeAt": 4102444800000})
        got = _run(page.render(), _visibility(_key(page)),
                   stored={f"crowgpt.dose.{_key(page)}": future})
        assert got["visible"] == 0

    def test_finishing_a_block_arms_the_lockout(self, pairs):
        page = PairPage(pairs, {}, seed=0, dose=5)
        got = _run(page.render(), _answer_block(_key(page)))
        assert got == {"answered": 5, "block": 1, "blocks": 3,
                       "next_block": 1, "rest_pending": True}

    def test_the_last_block_ends_without_a_lockout(self, pairs):
        page = PairPage(pairs, {}, seed=0, dose=5)
        got = _run(page.render(), _answer_block(_key(page)), stored={
            f"crowgpt.dose.{_key(page)}": json.dumps({"block": 2, "resumeAt": 0})})
        assert got["answered"] == 2 and got["block"] == 3
        assert got["next_block"] == 3 and got["rest_pending"] is False
