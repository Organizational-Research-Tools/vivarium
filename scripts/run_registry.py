"""Run registry: what ran, in what configuration, and how it ended — at a glance.

Scans a runs/ tree and prints the status table (passed / failed_score / unscored /
stalled / run_failed / incomplete, ⚠ = irregular), with config + score + cost. Pass a
runs root as the first arg (default ``runs/``); add ``--csv PATH`` / ``--jsonl PATH``
to also write the registry for analysis.

Run from repo root: `PYTHONPATH="$PWD" python scripts/run_registry.py [runs_root] [--csv out.csv]`
"""
from __future__ import annotations

import sys
from pathlib import Path

from oaos2.archive import render_run_registry, write_registry


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    runs_root = Path(args[0]) if args else Path("runs")
    if not runs_root.exists():
        print(f"no runs directory at {runs_root}")
        return 1
    print(render_run_registry(runs_root), end="")

    def _opt(flag):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None

    csv_path, jsonl_path = _opt("--csv"), _opt("--jsonl")
    if csv_path or jsonl_path:
        counts = write_registry(runs_root,
                                csv_path=Path(csv_path) if csv_path else None,
                                jsonl=Path(jsonl_path) if jsonl_path else None)
        print(f"\nwrote registry ({sum(counts.values())} runs): {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
