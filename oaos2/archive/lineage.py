"""File-lineage transcript + causal-lineage helpers (DESIGN §17.3, §9, §6.2).

The fourth standard transcript: the file/artifact lineage — for each path, the
ordered chain of capture events (write / edit / delete / contended) with their
before→after hashes and the tool call that caused them, plus the artifact-version
chain. Also exposes ``causal_ancestors`` — a multi-parent walk over
``caused_by_event_ids`` (§6.2) backing "what led to this commitment?" queries.
Pure read-side over the immutable trace; deterministic.
"""

from __future__ import annotations

from pathlib import Path

from oaos2.archive.transcript import events_in_order

_FILE_CLASSES = {"file.write", "file.edit", "file.delete", "file.write_contended",
                 "artifact.versioned"}


def _path_of(e: dict) -> str | None:
    p = e.get("payload") or {}
    return p.get("path") or p.get("file_path") or p.get("zone_path") or p.get("artifact_path")


def file_lineage(run_dir: Path, events: list[dict] | None = None) -> dict[str, list[dict]]:
    """``{path: [file-events in order]}`` reconstructed from the trace (§9 lineage)."""
    out: dict[str, list[dict]] = {}
    for e in (events if events is not None else events_in_order(run_dir)):
        if e.get("event_class") not in _FILE_CLASSES:
            continue
        path = _path_of(e) or "<unknown>"
        out.setdefault(path, []).append(e)
    return out


def render_file_lineage(run_dir: Path, events: list[dict] | None = None) -> str:
    """The ``file_lineage`` standard transcript (§17.3)."""
    lineage = file_lineage(run_dir, events)
    out = ["# File-lineage transcript", ""]
    if not lineage:
        out.append("(no file changes captured in this run)")
        return "\n".join(out) + "\n"
    for path in sorted(lineage):
        out.append(f"## {path}")
        for e in lineage[path]:
            p = e.get("payload") or {}
            before = (p.get("hash_before") or "—")[:16]
            after = (p.get("hash_after") or "—")[:16]
            who = e.get("agent_id") or "·"
            seq = e.get("sequence_number")
            out.append(f"[{seq:>5}] {who:<10} {e.get('event_class'):<22} {before}→{after}")
        out.append("")
    return "\n".join(out) + "\n"


def causal_ancestors(run_dir: Path, event_id: str) -> list[str]:
    """The transitive multi-parent ``caused_by`` ancestry of ``event_id`` (§6.2).

    A deterministic walk (sorted) over the causal DAG — what the assisted/unassisted
    label walk and "what led to this outcome?" queries are built on.
    """
    by_id = {e.get("event_id"): e for e in events_in_order(run_dir)}
    seen: set[str] = set()
    frontier = [event_id]
    while frontier:
        eid = frontier.pop()
        e = by_id.get(eid)
        if e is None:
            continue
        for parent in e.get("caused_by_event_ids") or []:
            if parent not in seen:
                seen.add(parent)
                frontier.append(parent)
    return sorted(seen)
