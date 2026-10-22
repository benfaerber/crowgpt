"""The weekly scheduler's one decision: is the published layer stale?"""

import importlib.util
import sys
from pathlib import Path

WORKER = Path(__file__).resolve().parents[1] / "worker" / "scout_scheduler.py"
spec = importlib.util.spec_from_file_location("scout_scheduler", WORKER)
scheduler = importlib.util.module_from_spec(spec)
sys.modules["scout_scheduler"] = scheduler
spec.loader.exec_module(scheduler)


class TestAge:
    def test_a_missing_layer_is_infinitely_stale(self, tmp_path):
        assert scheduler.age_s(tmp_path / "scout.json") == float("inf")

    def test_a_fresh_layer_is_young(self, tmp_path):
        layer = tmp_path / "scout.json"
        layer.write_text("{}")
        assert scheduler.age_s(layer) < scheduler.REBUILD_AFTER_S

    def test_a_week_old_layer_is_due(self, tmp_path):
        layer = tmp_path / "scout.json"
        layer.write_text("{}")
        week_on = layer.stat().st_mtime + scheduler.REBUILD_AFTER_S + 60
        assert scheduler.age_s(layer, now=week_on) > scheduler.REBUILD_AFTER_S

    def test_the_schedule_is_weekly(self):
        assert scheduler.REBUILD_AFTER_S == 7 * 24 * 3600
        assert scheduler.RETRY_AFTER_S < scheduler.REBUILD_AFTER_S
