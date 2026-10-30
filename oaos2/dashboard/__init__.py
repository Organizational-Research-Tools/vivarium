"""Browse saved runs and manage local research work through the dashboard.

The app displays runs, traces, files, comparisons, and annotations. It preserves
trace files but can save annotations, edit library YAML, and launch runs through
the workbench. Rebuildable caches speed up reading; annotations are separate
research data, not disposable cache entries. See docs/DASHBOARD.md.

The web app in app.py requires the dashboard dependency extra."""

from oaos2.dashboard.cache import RegistryCache
from oaos2.dashboard.store import arm_summary, filter_rows, list_runs, resolve_run_dir, run_detail

__all__ = [
    "RegistryCache",
    "arm_summary",
    "filter_rows",
    "list_runs",
    "resolve_run_dir",
    "run_detail",
]
