"""The engine names no task: everything specific to the materials workshop lives in its plug-in
(oaos2/tasks/plugins/materials_lab/), which registers its readers and its live standings panel with the engine's
open registries. This test fails if code outside the task plug-ins imports or names the workshop."""
from __future__ import annotations

import re
from pathlib import Path

OAOS2 = Path(__file__).resolve().parents[2] / "oaos2"
PLUGINS = OAOS2 / "tasks" / "plugins"
# the workshop's package and pack names, its study files, and the event classes only its pool records
NAMES = re.compile(r"materials_(lab|g\d|t1)|\bpc1|situation_pc1|lab\.staged|credit\.(allocated|awarded|voided|lapsed|"
                   r"restored)")


def test_no_engine_file_names_the_workshop():
    offenders = []
    for path in sorted(OAOS2.rglob("*")):
        if not path.is_file() or PLUGINS in path.parents or path.suffix not in (".py", ".html", ".json", ".yaml"):
            continue
        for i, line in enumerate(path.read_text(encoding="utf8", errors="ignore").splitlines(), 1):
            if NAMES.search(line):
                offenders.append(f"{path.relative_to(OAOS2.parent)}:{i}: {line.strip()[:100]}")
    assert not offenders, "engine code names the workshop:\n" + "\n".join(offenders)


def test_the_workshop_registers_its_live_standings_panel():
    from oaos2.dashboard import live

    events = [{"event_class": "lab.staged", "agent_id": "lab_a", "timestamp": 0.0, "payload": {}}]
    assert live.standings(events, "materials_lab") is None or isinstance(live.standings(events, "materials_lab"), dict)
    assert "materials_lab" in live._STANDINGS and live.standings(events, "no_such_pack") is None
