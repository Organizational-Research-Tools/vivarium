"""Deterministic exception-lifecycle projection (platform_theory_audit.md §11.4).

Researcher-facing exception queues, latencies, and coverage joins are derived
from recorded events here. Operational scheduling and grading queues are separate
runtime responsibilities. Any pack that files ``ExceptionRecord``-shaped items
in commitments matching ``source_prefix`` and disposes them through
``record_dispositions_cover``-shaped fields yields the same dataset.

Time is measured in commitment boundaries (the batched world's clock): the
latency of an exception is how many ``state.committed`` events elapsed between
its delivery/filing and its disposal, never wall-clock.
"""

from __future__ import annotations

import json
from pathlib import Path


class ExceptionProjectionError(ValueError):
    """The archive/schedule inputs cannot support a trustworthy projection."""


def _commit_events(events: list[dict]) -> list[dict]:
    rows = []
    for index, event in enumerate(events):
        if event.get("event_class") != "state.committed":
            continue
        state = (event.get("payload") or {}).get("state_commitment") or {}
        cid = state.get("commitment_id")
        if not cid:
            continue
        sequence = event.get("sequence_number")
        rows.append({
            "commitment_id": cid,
            "sequence_number": int(sequence) if isinstance(sequence, int) else index,
            "agent_id": state.get("agent_id") or event.get("agent_id"),
            "role_id": event.get("role_id"),
        })
    rows.sort(key=lambda row: row["sequence_number"])
    return rows


def _wave_delivery_sequences(events: list[dict]) -> dict[str, int]:
    """wave_id -> sequence of its FIRST delivered environment.event."""
    first: dict[str, int] = {}
    for index, event in enumerate(events):
        if event.get("event_class") != "environment.event":
            continue
        record = (event.get("payload") or {}).get("environment_event") or {}
        wave_id = record.get("wave_id")
        if not wave_id:
            continue
        sequence = event.get("sequence_number")
        sequence = int(sequence) if isinstance(sequence, int) else index
        if wave_id not in first or sequence < first[wave_id]:
            first[wave_id] = sequence
    return first


def _ref_index(schedule: dict | None) -> dict[str, dict]:
    """trigger-ref -> {packet_id, wave_id, rule_coverage, rule_ref, expected_scopes}."""
    if not schedule:
        return {}
    index: dict[str, dict] = {}
    for wave in schedule.get("waves") or []:
        for packet in wave.get("packets") or []:
            classification = packet.get("classification")
            if not isinstance(classification, dict):
                continue
            for ref in classification.get("refs") or []:
                if ref in index:  # the driver rejects this; fail loudly on stale inputs
                    raise ExceptionProjectionError(f"ambiguous classification ref {ref!r}")
                index[ref] = {
                    "packet_id": packet.get("packet_id"),
                    "wave_id": wave.get("wave_id"),
                    "rule_coverage": classification.get("rule_coverage"),
                    "rule_ref": classification.get("rule_ref"),
                    "expected_scopes": sorted(classification.get("expected_scopes") or []),
                }
    return index


def _boundaries_between(commits: list[dict], after: int, upto: int) -> int:
    """Count state.committed events with sequence in (after, upto]."""
    return sum(1 for row in commits if after < row["sequence_number"] <= upto)


def derive_exception_dataset(
    events: list[dict],
    submitted: dict[str, dict],
    *,
    source_prefix: str = "exception",
    records_field: str = "exception_records",
    id_field: str = "exception_id",
    dispositions_field: str = "exception_dispositions",
    schedule: dict | None = None,
) -> dict:
    """Derive per-exception lifecycle rows, the pending series, and a summary.

    ``events`` is the full ordered event stream; ``submitted`` maps commitment_id
    to its committed payload; ``schedule`` (optional, researcher-side) enables the
    oracle coverage join through classification ``refs``.
    """
    commits = _commit_events(events)
    committed_ids = {row["commitment_id"] for row in commits}
    wave_delivery = _wave_delivery_sequences(events)
    refs = _ref_index(schedule)

    filings: dict[str, dict] = {}
    duplicate_filings: list[dict] = []
    for row in commits:
        cid = row["commitment_id"]
        if not cid.startswith(source_prefix):
            continue
        payload = submitted.get(cid)
        records = payload.get(records_field) if isinstance(payload, dict) else None
        for record in records if isinstance(records, list) else []:
            if not isinstance(record, dict):
                continue
            rid = str(record.get(id_field, "")).strip()
            if not rid:
                continue
            if rid in filings:
                duplicate_filings.append({"exception_id": rid, "commitment_id": cid,
                                          "sequence_number": row["sequence_number"]})
                continue
            filings[rid] = {
                "exception_id": rid,
                "filed_commitment_id": cid,
                "filed_sequence": row["sequence_number"],
                "filed_by": row["agent_id"],
                "filed_by_role": row["role_id"],
                "trigger_refs": [str(r) for r in record.get("trigger_refs") or []],
                "affected_scopes": sorted(str(s) for s in record.get("affected_scopes") or []),
                "claimed_rule_ref": record.get("rule_ref"),
            }

    dispositions: dict[str, dict] = {}
    late_dispositions: list[dict] = []
    for row in commits:
        payload = submitted.get(row["commitment_id"])
        entries = payload.get(dispositions_field) if isinstance(payload, dict) else None
        if not isinstance(entries, dict):
            continue
        for rid in sorted(entries):
            entry = entries[rid]
            if not isinstance(entry, dict):
                continue
            found = {
                "disposition": entry.get("disposition"),
                "disposed_commitment_id": row["commitment_id"],
                "disposed_sequence": row["sequence_number"],
                "disposed_by": row["agent_id"],
                "repair_ref": entry.get("repair_ref"),
                "reason": entry.get("reason"),
            }
            if rid in dispositions:  # first explicit disposition closes; later ones recorded
                late_dispositions.append({"exception_id": rid, **found})
            else:
                dispositions[rid] = found

    unmatched_refs: set[str] = set()
    lifecycle: list[dict] = []
    for rid in sorted(filings):
        filing = dict(filings[rid])
        matches = []
        for ref in filing["trigger_refs"]:
            match = refs.get(ref)
            if match is None:
                if refs:
                    unmatched_refs.add(ref)
                continue
            matches.append(match)
        matched_waves = sorted({m["wave_id"] for m in matches if m.get("wave_id")})
        coverage_values = {m.get("rule_coverage") for m in matches}
        filing["matched_wave_ids"] = matched_waves
        filing["oracle_rule_coverage"] = (
            None if not matches
            else "exception" if "exception" in coverage_values
            else "rule_covered")
        filing["oracle_expected_scopes"] = sorted(
            {scope for m in matches for scope in m.get("expected_scopes") or []})
        delivery_sequences = [wave_delivery[w] for w in matched_waves if w in wave_delivery]
        filing["detection_boundaries"] = (
            _boundaries_between(commits, min(delivery_sequences), filing["filed_sequence"])
            if delivery_sequences else None)
        disposition = dispositions.get(rid)
        if disposition is not None:
            filing.update(disposition)
            filing["closure_boundaries"] = _boundaries_between(
                commits, filing["filed_sequence"], disposition["disposed_sequence"])
        else:
            filing["disposition"] = None
            filing["closure_boundaries"] = None
        lifecycle.append(filing)

    orphan_dispositions = sorted(set(dispositions) - set(filings))

    pending_series: list[dict] = []
    open_ids: set[str] = set()
    filed_at = {rid: filings[rid]["filed_sequence"] for rid in filings}
    disposed_at = {rid: d["disposed_sequence"] for rid, d in dispositions.items()
                   if rid in filings}
    for row in commits:
        sequence = row["sequence_number"]
        open_ids = {rid for rid in filings
                    if filed_at[rid] <= sequence
                    and disposed_at.get(rid, sequence + 1) > sequence}
        pending_series.append({
            "commitment_id": row["commitment_id"],
            "sequence_number": sequence,
            "pending_count": len(open_ids),
            "pending_ids": sorted(open_ids),
        })

    disposed_rows = [row for row in lifecycle if row["disposition"] is not None]
    by_disposition: dict[str, int] = {}
    for row in disposed_rows:
        by_disposition[row["disposition"]] = by_disposition.get(row["disposition"], 0) + 1
    closure_values = [row["closure_boundaries"] for row in disposed_rows]
    summary = {
        "n_filed": len(lifecycle),
        "n_disposed": len(disposed_rows),
        "n_unresolved": len(lifecycle) - len(disposed_rows),
        "unresolved_ids": sorted(rid for rid in filings if rid not in dispositions),
        "by_disposition": {k: by_disposition[k] for k in sorted(by_disposition)},
        "by_oracle_coverage": _coverage_counts(lifecycle),
        "max_pending": max((row["pending_count"] for row in pending_series), default=0),
        "mean_closure_boundaries": (
            round(sum(closure_values) / len(closure_values), 6) if closure_values else None),
        "unmatched_trigger_refs": sorted(unmatched_refs),
        "duplicate_filings": duplicate_filings,
        "late_dispositions": late_dispositions,
        "orphan_disposition_ids": orphan_dispositions,
        "n_commitments": len(committed_ids),
    }
    return {"lifecycle": lifecycle, "pending_series": pending_series, "summary": summary}


def _coverage_counts(lifecycle: list[dict]) -> dict[str, int]:
    counts = {"rule_covered": 0, "exception": 0, "unjoined": 0}
    for row in lifecycle:
        coverage = row.get("oracle_rule_coverage")
        counts[coverage if coverage in ("rule_covered", "exception") else "unjoined"] += 1
    return counts


def derive_exception_report(run_root: Path | str, *, schedule_path: Path | str | None = None,
                            **conventions) -> dict:
    """Load a run archive (and optionally its researcher-side schedule) and project."""
    from oaos2.trace.invariants import load_all_events

    run_root = Path(run_root)
    submitted: dict[str, dict] = {}
    roots = (run_root / "captured" / "submitted", run_root / "submitted")
    source = next((root for root in roots if root.is_dir()), None)
    if source is not None:
        for path in sorted(source.glob("*.json")):
            try:
                submitted[path.stem] = json.loads(path.read_text())
            except ValueError:
                continue
    schedule = None
    if schedule_path is not None:
        schedule = json.loads(Path(schedule_path).read_text())
    return derive_exception_dataset(
        load_all_events(run_root), submitted, schedule=schedule, **conventions)
