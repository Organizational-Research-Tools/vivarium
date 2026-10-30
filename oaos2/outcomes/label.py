"""Label an outcome from interventions on its recorded causal paths.

Starting from accepted commitment events, follow caused_by_event_ids and look
for interventions classified as recorded or treatment_defining. Finding one
returns assisted; otherwise the result is unassisted. Structural parent_event_id
links are not followed: grouping an event under a turn does not establish a
causal contribution. Unlinked or unrecorded influences cannot be detected here."""

from __future__ import annotations

from pathlib import Path

from oaos2.trace.invariants import load_all_events

_BLOCKING_CLASSES = frozenset({"recorded", "treatment_defining"})


def _ancestors(start_ids: list[str], parents: dict[str, list[str]]) -> set[str]:
    """BFS over the multi-parent caused_by DAG (every edge, M0 §4)."""
    seen: set[str] = set()
    frontier = list(start_ids)
    while frontier:
        e = frontier.pop()
        for p in parents.get(e, ()):
            if p not in seen:
                seen.add(p)
                frontier.append(p)
    return seen


def label_outcome(run_dir: Path, commit_event_ids: list[str]) -> str:
    """Label an outcome assisted/unassisted from its ``state.committed`` event ids."""
    events = load_all_events(run_dir)
    return label_outcome_from_events(events, commit_event_ids)


def label_outcome_from_events(events: list[dict], commit_event_ids: list[str]) -> str:
    parents: dict[str, list[str]] = {}
    by_id: dict[str, dict] = {}
    for e in events:
        parents[e["event_id"]] = list(e.get("caused_by_event_ids", []))
        by_id[e["event_id"]] = e

    # Include the commit events themselves in the ancestry set.
    ancestry = set(commit_event_ids) | _ancestors(commit_event_ids, parents)
    for eid in ancestry:
        e = by_id.get(eid)
        if e is None or e["event_class"] != "intervention.recorded":
            continue
        if (e.get("payload") or {}).get("class") in _BLOCKING_CLASSES:
            return "assisted"
    return "unassisted"
