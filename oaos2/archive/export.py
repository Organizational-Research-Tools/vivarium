"""Write readable views and metrics into a run's derived/ directory.

render_archive() writes clean, full, per-agent, and file-history transcripts,
metrics.json, and any registered task report. It reads events once and shares
them with renderers; individual views may also read model responses, settings,
captured files, and task materials. It overwrites derived outputs on repeated
calls while preserving source evidence. Reproducibility requires the same
saved inputs and rendering code."""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.archive.datasets import compute_metrics
from oaos2.archive.lineage import render_file_lineage
from oaos2.archive.renderers import write_pack_report
from oaos2.archive.transcript import (
    events_in_order,
    render_agent_centric,
    render_clean,
    render_full,
)

_TRANSCRIPTS = {
    "clean.txt": render_clean,
    "full.txt": render_full,
    "agent_centric.txt": render_agent_centric,
    "file_lineage.txt": render_file_lineage,
}


def render_archive(run_dir: Path) -> Path:
    """Write standard transcripts, metrics, and a registered task report to derived/.

    Return the derived directory path. Repeated calls overwrite these outputs.
    Events are loaded once; individual renderers may read additional saved evidence."""
    run_dir = Path(run_dir)
    derived = run_dir / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    events = events_in_order(run_dir)  # single read for all renderers
    for filename, render in _TRANSCRIPTS.items():
        (derived / filename).write_text(render(run_dir, events))
    metrics = compute_metrics(run_dir, events)
    (derived / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True))
    # The pack's registered report (archive/renderers.py), if it has one — run
    # after and apart from the foundation files, so a pack failure records
    # itself under derived/ and never costs the transcripts or metrics.
    write_pack_report(run_dir, events)
    return derived


def render_sweep(run_dirs: list[Path]) -> list[Path]:
    """Render ``derived/`` for every run in a sweep (convenience)."""
    return [render_archive(rd) for rd in run_dirs]
