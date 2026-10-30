"""Summarize materials_lab runs from their archives for the phase 5 comparison
(director with measurement-only helpers against peers). Reads trace/events.jsonl only;
no model, no Docker.

Run from the repository root:
  PYTHONPATH="$PWD" python scripts/materials_lab_report.py runs/<experiment_root> [--json out.json]

The summary is the pack's registered report (``oaos2.tasks.plugins.materials_lab.derived``),
which the dashboard and the run registry also read. Per run: preset, model, calls, cost,
and output tokens per role; observation units used per lab; prototypes registered per role; measurements per role with how many were on another
agent's prototype (executed requests); records shared; posts and notes per role; reports
submitted with public kind, credit, and the private assessment's attribution and omission
flags; projects qualified honestly; concerns; retirements. Which requests were routine
procurement and which delegated an investigation is coded by a reader from the message
texts, which this report lists verbatim; it does not code them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from oaos2.tasks.plugins.materials_lab.derived import summarize_run as _summarize_run


def _find_runs(root: Path) -> list[Path]:
    return sorted({p.parent.parent for p in root.glob("**/trace/events.jsonl")})


def summarize_run(run_dir: Path) -> dict:
    """The pack's registered report (``oaos2.tasks.plugins.materials_lab.derived``),
    with the run directory added for the printed listing."""
    return {"run_dir": str(run_dir), **_summarize_run(Path(run_dir))}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    rows = [summarize_run(r) for r in _find_runs(root)]
    for r in rows:
        print(f"{Path(r['run_dir']).name}: preset={r['preset']} cost={r['cost_usd']} honest_credits={r.get('honest_credits')} "
              f"credited_violations={r.get('credited_violations')} voided={r.get('voided_violations')} "
              f"projects_qualified_honestly={r['projects_qualified_honestly']} reports_with_violation={r['reports_with_violation']} "
              f"concerns={len(r['concerns'])}")
        for rep in r.get("reports") or []:
            print(f"    {rep['report_id']} {rep['author']} {rep['project']}: {rep.get('disposition')}")
        for pid, a in sorted(r["achievements"].items()):
            print(f"    {pid} ({a['type']}): prototypes={a['prototypes']} fewest_violations={a['fewest_violations']} "
                  f"compatible registered={a['fully_compatible_registered']} measured_on_3={a['fully_compatible_measured_on_3']} "
                  f"full_panels_on_3={a['fully_compatible_full_panels_on_3']} qualifying registered={a['honest_qualifying_registered']} "
                  f"with_panels={a['honest_qualifying_full_panels_on_3']}")
        for role, s in r["roles"].items():
            print(f"    {role}: calls={s['calls']} units={s['units_used']} prototypes={s['prototypes']} "
                  f"measured={s['measurements']} (for others {s['measurements_for_others']}) shares={s['shares']} "
                  f"posts={s['posts']} notes={s['notes']} reports={s['reports']} credits={s['credits']}")
    if "--json" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--json") + 1])
        out.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")
        print(f"written {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
