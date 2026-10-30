"""Build transcripts, file histories, and analysis tables from saved run evidence.

render_archive writes standard views and metrics into derived/. Other helpers
export run rows or follow causal links. These outputs can be rebuilt from the
same evidence and analysis code; they do not replace the saved event record.
Task-specific reports may also read captured submissions and pinned materials."""

from oaos2.archive.datasets import (
    compute_metrics,
    run_row,
    runs_to_csv,
    runs_to_jsonl,
)
from oaos2.archive.export import render_archive, render_sweep
from oaos2.archive.lineage import causal_ancestors, file_lineage, render_file_lineage
from oaos2.archive.registry import (
    disposition,
    render_run_registry,
    run_record,
    scan_runs,
    write_registry,
)
from oaos2.archive.transcript import (
    render_agent_centric,
    render_clean,
    render_full,
)

__all__ = [
    "render_archive",
    "render_sweep",
    "compute_metrics",
    "run_row",
    "runs_to_jsonl",
    "runs_to_csv",
    "file_lineage",
    "causal_ancestors",
    "render_file_lineage",
    "render_agent_centric",
    "render_clean",
    "render_full",
    "disposition",
    "run_record",
    "scan_runs",
    "render_run_registry",
    "write_registry",
]
