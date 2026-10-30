"""The cap guard reads a model's observed spend per laboratory-minute from its earlier runs (October 16, 2026)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from run_materials_lab_smoke import observed_spend_per_lab_minute  # noqa: E402


def _run(root: Path, name: str, model: str, cost: float, minutes: float, labs: int = 6, closed: bool = True):
    d = root / "pc1" / name / "materials_lab" / "r1"
    (d / "trace").mkdir(parents=True)
    (d / "run_status.json").write_text(json.dumps({"model_ref": model, "cost_usd": cost, "closed": closed}))
    events = [{"event_class": "run.started", "timestamp": 0.0}]
    events += [{"event_class": "model.responded", "timestamp": minutes * 60, "agent_id": f"lab_{i}"} for i in range(labs)]
    (d / "trace" / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")


def test_the_highest_observed_rate_of_the_same_model_is_used(tmp_path):
    _run(tmp_path, "a", "openrouter/m@h", cost=6.0, minutes=50)    # 0.02 a lab-minute
    _run(tmp_path, "b", "openrouter/m@h", cost=5.0, minutes=33.3)  # capped early: about 0.025
    _run(tmp_path, "c", "openrouter/other", cost=50.0, minutes=50)
    _run(tmp_path, "d", "openrouter/m@h", cost=9.0, minutes=50, closed=False)  # unfinished: not read
    rate, n = observed_spend_per_lab_minute("openrouter/m@h", tmp_path)
    assert n == 2 and abs(rate - 5.0 / (6 * 33.3)) < 1e-6
    assert observed_spend_per_lab_minute("openrouter/none", tmp_path) is None
