"""Registered work views (DASHBOARD.md §4.2c): the task-specific state of a run.

What a run was working on — cases for the budget office, projects and prototypes
for the materials lab — is the pack's own knowledge. A pack registers a
``WorkAdapter`` from its ``derived`` module (the same import convention as
``renderers.py``): a tab label and a function that turns the run's events and its
registered report into plain sections. The dashboard shows whatever sections come
back and names the tab as the pack does; a pack without one has no Work tab, and
the case dossier stays the view for packs with environment arrivals.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# sections(run_dir, events, report) -> [{"title", "note"?, "columns": [...], "rows": [[...], ...]}
#                                       | {"title", "note"?, "kv": [(k, v), ...]}]
Sections = Callable[[Path, list[dict], dict | None], list[dict]]


@dataclass(frozen=True)
class WorkAdapter:
    pack_id: str
    label: str
    sections: Sections


_ADAPTERS: dict[str, WorkAdapter] = {}


def register_work_adapter(adapter: WorkAdapter, *, override: bool = False) -> None:
    if adapter.pack_id in _ADAPTERS and not override:
        raise ValueError(f"work adapter for {adapter.pack_id!r} already registered")
    _ADAPTERS[adapter.pack_id] = adapter


def unregister_work_adapter(pack_id: str) -> None:
    """Test seam only."""
    _ADAPTERS.pop(pack_id, None)


def work_adapter_for(pack_id: str | None) -> WorkAdapter | None:
    from oaos2.archive.renderers import ensure_pack_renderers  # same convention module
    ensure_pack_renderers(pack_id)
    return _ADAPTERS.get(pack_id) if pack_id else None


def work_sections(pack_id: str | None, run_dir: Path, events: list[dict],
                  report: dict | None) -> list[dict]:
    adapter = work_adapter_for(pack_id)
    if adapter is None:
        return []
    out = []
    for sec in adapter.sections(Path(run_dir), events, report) or []:
        if not isinstance(sec, dict) or "title" not in sec or not ("rows" in sec or "kv" in sec):
            continue  # a malformed section is dropped, never shown with invented fields
        out.append(sec)
    return out
