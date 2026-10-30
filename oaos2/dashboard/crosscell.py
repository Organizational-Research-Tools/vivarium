"""Cross-cell reading: the item × cell matrix, the coverage ledger, the work queue
(DASHBOARD.md §4.12).  Read-only; verdicts come from each run's pack report (the
report store), coverage from the annotation links written under ``reading`` and
the codebook namespaces.  Nothing here recomputes a scorer."""

from __future__ import annotations

import re
from pathlib import Path

from oaos2.annotations.link_writer import load_links
from oaos2.archive.design import cell_of
from oaos2.archive.items import item_adapter_for

# outcome label → glyph (the frozen scorer's vocabulary; unknown labels show as ·)
GLYPHS = {
    "rule_applied": "✓", "exception_repaired": "●", "exception_repaired_late": "◐",
    "exception_repaired_unjoined": "◑", "exception_repaired_wrong_choice": "✗",
    "exception_repaired_choice_undetermined": "?", "exception_unresolved": "○",
    "exception_dangling_repair": "⊘", "covered_unhandled": "▽", "affected_programs_dropped": "—",
}
ATTENTION = {"exception_repaired_wrong_choice", "exception_repaired_choice_undetermined",
             "exception_unresolved", "exception_dangling_repair", "covered_unhandled"}


def _natural(s: str) -> tuple:
    return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s))


def _coverage(run_dir: Path) -> dict[str, dict]:
    """``item_id → {read: [modes], coded: [refs]}`` from the run's annotation links."""
    out: dict[str, dict] = {}
    for link in load_links(run_dir):
        label = link.get("label") or {}
        iid = label.get("item_id")
        if not iid:
            continue
        slot = out.setdefault(iid, {"read": [], "coded": []})
        if link.get("namespace") == "reading":
            slot["read"].append(label.get("mode") or "?")
        else:
            slot["coded"].append(link.get("label_schema_ref"))
    return out


def matrix(rows: list[dict], reports, *, by: str = "arm") -> dict:
    """Items × cells for one experiment's registry rows.  ``by="rep"`` orders the
    columns replicate-major so paired arms sit side by side."""
    cells = []
    for r in rows:
        run_dir = Path(r["run_dir"])
        cell = cell_of({"run_id": r.get("run_id"), "organization_id": r.get("organization_id"),
                        "extensions": {"difficulty": r.get("difficulty")}})
        rep = reports.get(run_dir)
        adapter = item_adapter_for(r.get("task_pack_id"))
        scored = adapter.score_rows(rep["report"]) if (adapter and rep.get("report")) else {}
        cells.append({"run_ref": r["run_ref"], "run_id": r.get("run_id"), "org": r.get("organization_id"),
                      "tier": r.get("difficulty"), "rep": cell["rep"], "status": r.get("status"),
                      "report_source": rep.get("source"), "scored": scored,
                      "coverage": _coverage(run_dir), "retained": r.get("retained_fraction")})
    key = ((lambda c: (c["rep"] if c["rep"] is not None else 10**6, c["org"] or "", c["tier"] or ""))
           if by == "rep" else (lambda c: (c["org"] or "", c["tier"] or "", c["rep"] if c["rep"] is not None else 10**6)))
    cells.sort(key=key)
    items = sorted({iid for c in cells for iid in c["scored"]} | {iid for c in cells for iid in c["coverage"]},
                   key=_natural)
    grid = []
    for iid in items:
        row = {"item_id": iid, "cells": [], "n_attention": 0, "n_read": 0}
        for c in cells:
            s = c["scored"].get(iid)
            cov = c["coverage"].get(iid) or {"read": [], "coded": []}
            outcome = s.get("outcome") if s else None
            entry = {"run_ref": c["run_ref"], "outcome": outcome, "glyph": GLYPHS.get(outcome, "·") if s else "",
                     "verdict": s.get("verdict") if s else None, "verdict_source": s.get("verdict_source") if s else None,
                     "lost": s.get("lost_benefit") if s else None, "attention": outcome in ATTENTION,
                     "read": cov["read"], "coded": cov["coded"]}
            row["n_attention"] += 1 if entry["attention"] else 0
            row["n_read"] += 1 if cov["read"] else 0
            row["cells"].append(entry)
        grid.append(row)
    queue = [{"item_id": g["item_id"], "run_ref": e["run_ref"], "outcome": e["outcome"],
              "verdict": e["verdict"], "verdict_source": e["verdict_source"]}
             for g in grid for e in g["cells"] if e["attention"] and not e["read"]]
    per_cell = [{"run_ref": c["run_ref"], "org": c["org"], "tier": c["tier"], "rep": c["rep"],
                 "n_items": len(c["scored"]), "n_attention": sum(1 for s in c["scored"].values() if s.get("outcome") in ATTENTION),
                 "n_read": sum(1 for iid in c["scored"] if c["coverage"].get(iid, {}).get("read")),
                 "n_coded": sum(1 for iid in c["scored"] if c["coverage"].get(iid, {}).get("coded")),
                 "retained": c["retained"], "report_source": c["report_source"]} for c in cells]
    return {"cells": cells, "item_ids": items, "grid": grid, "queue": queue, "per_cell": per_cell,
            "n_rendered": sum(1 for c in cells if c["report_source"] in ("rendered", "store")),
            "glyphs": GLYPHS}
