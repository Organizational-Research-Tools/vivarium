"""Registered exchange readers (DASHBOARD.md §4.4): what one agent did toward named
others, beyond messages.

A task's directed actions — granting a measurement, sharing a record, disclosing a
composition — are communication in substance, but their event classes belong to the
pack's own vocabulary and shared code must not list them. A pack registers an
``ExchangeAdapter`` from its ``derived`` module (the same import convention as
``renderers.py``), and the communication views look it up by the run manifest's
``task_pack_id``. Rows are observables: who acted toward whom, when, and a short
summary; whether an action answered a request is a reading, not a row.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Rows = Callable[[list[dict]], list[dict]]

ROW_KEYS = ("seq", "event_id", "from", "to", "kind", "text")


@dataclass(frozen=True)
class ExchangeAdapter:
    """``rows(events)`` returns ``[{seq, event_id, from, to: [role, ...], kind, text}]``
    for the directed actions the pack treats as exchanges, in any order.
    ``milestones(events)``, optional, returns rows in the same shape for the task's
    turning points a reader of the run's story should see (a report submitted, a
    credit awarded); ``to`` may be empty."""

    pack_id: str
    rows: Rows
    milestones: Rows | None = None


_ADAPTERS: dict[str, ExchangeAdapter] = {}


def register_exchange_adapter(adapter: ExchangeAdapter, *, override: bool = False) -> None:
    if adapter.pack_id in _ADAPTERS and not override:
        raise ValueError(f"exchange adapter for {adapter.pack_id!r} already registered")
    _ADAPTERS[adapter.pack_id] = adapter


def unregister_exchange_adapter(pack_id: str) -> None:
    """Test seam only."""
    _ADAPTERS.pop(pack_id, None)


def exchange_adapter_for(pack_id: str | None) -> ExchangeAdapter | None:
    from oaos2.archive.renderers import ensure_pack_renderers  # same convention module
    ensure_pack_renderers(pack_id)
    return _ADAPTERS.get(pack_id) if pack_id else None


def exchange_rows(pack_id: str | None, events: list[dict]) -> list[dict]:
    """The pack's exchange rows in writer order, or ``[]`` for a pack without an
    adapter. A malformed row is dropped rather than shown with invented fields."""
    adapter = exchange_adapter_for(pack_id)
    if adapter is None:
        return []
    out = []
    for row in adapter.rows(events) or []:
        if not isinstance(row, dict) or any(k not in row for k in ROW_KEYS):
            continue
        out.append({**row, "to": sorted(str(t) for t in (row.get("to") or []))})
    return sorted(out, key=lambda r: (r["seq"] or 0, r["event_id"] or ""))


def milestone_rows(pack_id: str | None, events: list[dict]) -> list[dict]:
    """The pack's story milestones in writer order, or ``[]``."""
    adapter = exchange_adapter_for(pack_id)
    if adapter is None or adapter.milestones is None:
        return []
    out = []
    for row in adapter.milestones(events) or []:
        if not isinstance(row, dict) or any(k not in row for k in ROW_KEYS):
            continue
        out.append({**row, "to": sorted(str(t) for t in (row.get("to") or []))})
    return sorted(out, key=lambda r: (r["seq"] or 0, r["event_id"] or ""))
