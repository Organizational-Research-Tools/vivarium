"""Index saved dataset rows for comparison with a displayed task report.

Read JSON files under library/experiments/evidence with dataset.rows keyed by
run_id. This index does not validate preregistration status or select the most
authoritative correction. If files repeat a run ID, the last filename in sorted
order wins. Check the named evidence file against the study's results of record.
The displayed task report may itself be a saved file rather than a fresh render.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from oaos2.library import library_dir

_snapshot: dict | None = None
_snapshot_key: tuple | None = None
_left_out: dict[str, dict] = {}


def _evidence_dir() -> Path:
    return library_dir() / "experiments" / "evidence"


def frozen_rows() -> dict[str, dict]:
    """``run_id → frozen row`` over every evidence dataset (memoized on file mtimes)."""
    global _snapshot, _snapshot_key, _left_out
    d = _evidence_dir()
    files = sorted(d.glob("*.json")) if d.exists() else []
    key = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    if _snapshot is not None and key == _snapshot_key:
        return _snapshot
    rows: dict[str, dict] = {}
    left_out: dict[str, dict] = {}
    for f in files:
        try:
            raw = f.read_bytes()
            doc = json.loads(raw)
        except (OSError, ValueError):
            continue
        dataset = doc.get("dataset") if isinstance(doc, dict) else None
        if not isinstance(dataset, dict) or not isinstance(dataset.get("rows"), list):
            continue
        sha = "sha256:" + hashlib.sha256(raw).hexdigest()
        for row in dataset["rows"]:
            rid = row.get("run_id") if isinstance(row, dict) else None
            if rid:
                rows[rid] = {**row, "_evidence_file": f.name, "_evidence_sha256": sha}
        # Runs the dataset's own audit left out (``audit.excluded`` / ``audit.nonqualifying``,
        # keyed by run folder name), with its stated reason.
        audit = dataset.get("audit") if isinstance(dataset.get("audit"), dict) else {}
        for kind in ("excluded", "nonqualifying"):
            for entry in audit.get(kind) or []:
                name = entry.get("run_dir") if isinstance(entry, dict) else None
                if name:
                    left_out[Path(str(name)).name] = {"kind": kind, "reason": entry.get("reason"),
                                                      "_evidence_file": f.name}
    _snapshot, _snapshot_key, _left_out = rows, key, left_out
    return rows


def left_out_of_dataset(run_dir_name: str | None) -> dict | None:
    """``{"kind": "excluded"|"nonqualifying", "reason", "_evidence_file"}`` when a saved
    evidence dataset's audit left this run out, else None. The dataset's own record;
    which dataset governs a study is its results document's decision."""
    frozen_rows()
    return _left_out.get(run_dir_name) if run_dir_name else None


def frozen_for(run_id: str | None) -> dict | None:
    return frozen_rows().get(run_id) if run_id else None


def evidence_for(run_ids: set[str]) -> list[dict]:
    """Saved evidence datasets that contain any of these runs, with their registered
    decisions when the analysis saved them in the standard form: a top-level
    ``decisions`` list of ``{hypothesis, rule, result, estimate?, note?}`` where
    ``result`` is ``supported``, ``not_supported`` or ``inconclusive``. The dashboard
    shows what the analysis saved; it never applies a rule itself."""
    d = _evidence_dir()
    out = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        try:
            doc = json.loads(f.read_bytes())
        except (OSError, ValueError):
            continue
        dataset = doc.get("dataset") if isinstance(doc, dict) else None
        if not isinstance(dataset, dict) or not isinstance(dataset.get("rows"), list):
            continue
        ids = {r.get("run_id") for r in dataset["rows"] if isinstance(r, dict)}
        shared = ids & run_ids
        if not shared:
            continue
        decisions = doc.get("decisions") if isinstance(doc.get("decisions"), list) else None
        out.append({"file": f.name, "n_rows": len(ids), "n_shared": len(shared),
                    "decisions": [x for x in decisions or [] if isinstance(x, dict)] or None,
                    "analyses": sorted(doc["analyses"]) if isinstance(doc.get("analyses"), dict) else [],
                    "results_doc": doc.get("results_doc") if isinstance(doc.get("results_doc"), str) else None})
    return out
