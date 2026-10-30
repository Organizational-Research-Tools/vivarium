"""Registered derived-report renderers (DASHBOARD.md §5 seam; DESIGN §17.3).

A task pack may ship an archive-side report — budget_execution's delivery-rule
analysis is the first — that the registry, the dashboard, and ``render_archive``
all want.  The foundation never names a pack's report file: a pack registers a
``DerivedRenderer`` under its ``pack_id`` and everything looks it up by the run
manifest's ``task_pack_id``.  Registration happens on import of the pack's
``oaos2.tasks.plugins.<pack_id>.derived`` module (a convention rather than a
manifest key, because every run pins the task manifest's hash and a manifest
edit would mark every existing archive as stale materials).

Contract a renderer must keep (the same bar as the transcripts): a pure function
of the frozen archive plus hash-pinned library assets — verify the pins and raise
on drift, never fall back to current materials — sorted keys, no wall-clock, so a
re-render is byte-identical.  ``identity`` names the analysis code that produced a
report (a hash of the renderer's source), so a rendered-at-HEAD number can always
be told apart from a file written at finalize.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import inspect
import json
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Render = Callable[[Path, list[dict]], dict]
Summary = Callable[[dict], dict]


@dataclass(frozen=True)
class DerivedRenderer:
    """One pack's archive-side report.

    ``render(run_dir, events)`` returns the JSON-able report; ``summary(report)``
    flattens it into the registry's per-run columns (``retained_fraction`` and the
    like — whatever the pack wants scannable).  ``identity`` is the analysis-code
    fingerprint; left empty it is derived from the render function's module.
    ``expects`` names the top-level keys the current analysis produces; a saved report
    without one of them predates that analysis, and a reader may render afresh.
    ``verdict_note`` says what the scorer's pass/fail counts."""

    pack_id: str
    filename: str
    render: Render
    summary: Summary
    identity: str = ""
    expects: tuple[str, ...] = ()
    # What the task's pass/fail verdict counts, in one short sentence, shown beside the
    # verdict so that a reader does not take it for the study's outcome.
    verdict_note: str = ""
    # Summary keys that describe the run's condition as recorded (an institution, how a
    # rung was seeded) rather than its result; the runs table shows them and the
    # exploratory condition summaries group by them.
    condition_keys: tuple[str, ...] = ()
    # ``outcome(summary)`` → ``{"label", "category"?, "value"?, "detail"?}`` or None: the
    # task's central measure for one run, in its own terms (there is no platform-wide
    # pass/fail). ``category`` groups runs by kind of outcome; ``value`` is numeric.
    outcome: Callable[[dict], dict | None] | None = None
    # ``eligibility(summary)`` → reasons, beyond the platform's completion criteria, why
    # this run cannot enter results (e.g. an assessment did not complete); [] if none.
    eligibility: Callable[[dict], list[str]] | None = None
    # ``notes(summary)`` → descriptive conditions a reader should see beside eligibility but
    # that a study's registered rules may include or exclude (e.g. the run ended because
    # classifier refusals exceeded the bound). A note never makes a run ineligible; that is
    # for conditions no study can waive (lineage audit F05, October 19, 2026).
    notes: Callable[[dict], list[str]] | None = None


_REGISTRY: dict[str, DerivedRenderer] = {}
_TRIED: set[str] = set()


def module_identity(obj) -> str:
    """``sha256:<16 hex>`` of the source file defining ``obj`` (a module or function)."""
    try:
        src = inspect.getsourcefile(obj)
        if not src:
            return "unknown"
        return "sha256:" + hashlib.sha256(Path(src).read_bytes()).hexdigest()[:16]
    except (TypeError, OSError):
        return "unknown"


def register_derived_renderer(renderer: DerivedRenderer, *, override: bool = False) -> None:
    if renderer.pack_id in _REGISTRY and not override:
        raise ValueError(f"derived renderer for {renderer.pack_id!r} already registered "
                         "(pass override=True)")
    if not renderer.identity:
        renderer = dataclasses.replace(renderer, identity=module_identity(renderer.render))
    _REGISTRY[renderer.pack_id] = renderer


def unregister_derived_renderer(pack_id: str) -> None:
    """Test seam only — a registry entry is otherwise process-lifetime."""
    _REGISTRY.pop(pack_id, None)
    _TRIED.discard(pack_id)


def ensure_pack_renderers(pack_id: str | None) -> None:
    """Import ``oaos2.tasks.plugins.<pack_id>.derived`` once, if it exists."""
    if not pack_id or pack_id in _REGISTRY or pack_id in _TRIED:
        return
    _TRIED.add(pack_id)
    modname = f"oaos2.tasks.plugins.{pack_id}.derived"
    try:
        importlib.import_module(modname)
    except ModuleNotFoundError as exc:
        # No derived module (or no plugin package at all) is the ordinary case;
        # a *nested* missing import inside an existing module is a real error.
        if exc.name and modname.startswith(exc.name):
            return
        raise


def derived_renderer_for(pack_id: str | None) -> DerivedRenderer | None:
    ensure_pack_renderers(pack_id)
    return _REGISTRY.get(pack_id) if pack_id else None


def registered_filenames() -> frozenset[str]:
    return frozenset(r.filename for r in _REGISTRY.values())


def task_pack_id_of(run_dir: Path) -> str | None:
    try:
        return json.loads((Path(run_dir) / "manifest.json").read_text()).get("task_pack_id")
    except (OSError, ValueError):
        return None


def report_text(report: dict) -> str:
    """The one serialization every writer uses — byte-identity across paths depends on it."""
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_pack_report(run_dir: Path, events: list[dict],
                       renderer: DerivedRenderer | None = None) -> dict:
    """Render (never write) the pack report for a run.

    Returns ``{"report", "source", "identity", "filename", "error"}`` where
    ``source`` is ``"rendered"`` on success, ``"error"`` on a renderer failure
    (pin drift, missing payload, …), or ``None`` when the pack has no renderer."""
    run_dir = Path(run_dir)
    renderer = renderer or derived_renderer_for(task_pack_id_of(run_dir))
    if renderer is None:
        return {"report": None, "source": None, "identity": None, "filename": None, "error": None}
    try:
        report = renderer.render(run_dir, events)
    except Exception as exc:  # noqa: BLE001 — surfaced, never swallowed
        return {"report": None, "source": "error", "identity": renderer.identity,
                "filename": renderer.filename,
                "error": f"{type(exc).__name__}: {exc}"[:400]}
    return {"report": report, "source": "rendered", "identity": renderer.identity,
            "filename": renderer.filename, "error": None}


def load_pack_report_file(run_dir: Path, renderer: DerivedRenderer | None = None) -> dict | None:
    """The report as written under ``derived/`` at finalize (or by a sweep), if any."""
    run_dir = Path(run_dir)
    renderer = renderer or derived_renderer_for(task_pack_id_of(run_dir))
    if renderer is None:
        return None
    path = run_dir / "derived" / renderer.filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def write_pack_report(run_dir: Path, events: list[dict]) -> Path | None:
    """``render_archive``'s hook: write the pack report under ``derived/``, isolated.

    A renderer failure never masks the foundation transcripts — it lands in
    ``derived/RENDER_ERROR.<filename>.txt`` naming the renderer, and the four
    transcripts + metrics stay as rendered."""
    run_dir = Path(run_dir)
    renderer = derived_renderer_for(task_pack_id_of(run_dir))
    if renderer is None:
        return None
    derived = run_dir / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    target = derived / renderer.filename
    error_file = derived / f"RENDER_ERROR.{renderer.filename}.txt"
    try:
        report = renderer.render(run_dir, events)
    except Exception:  # noqa: BLE001 — recorded beside the archive, never raised
        error_file.write_text(
            f"derived renderer {renderer.pack_id!r} ({renderer.filename}, "
            f"identity {renderer.identity}) failed:\n{traceback.format_exc()}")
        return None
    target.write_text(report_text(report))
    if error_file.exists():
        error_file.unlink()  # a later successful render supersedes the error record
    return target
