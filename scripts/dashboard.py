"""Launch the local dashboard for inspecting runs and managing research work.

The server binds to 127.0.0.1. It preserves trace files; its workbench can save
annotations, edit library settings, and launch runs. See docs/DASHBOARD.md.

Run from the repository root after installing the dashboard extra:
  PYTHONPATH="$PWD" python scripts/dashboard.py [runs_root] [--port 8722]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    try:
        import uvicorn
        from oaos2.dashboard.app import create_app
    except ImportError as exc:
        if exc.name and exc.name.split(".")[0] == "oaos2":
            # Not a missing package — the oaos2 source isn't on sys.path. Run from
            # repo root with PYTHONPATH set (CLAUDE.md workflow rule).
            print('cannot import oaos2 — run from the repo root with PYTHONPATH set:\n'
                  '  PYTHONPATH="$PWD" python scripts/dashboard.py [runs_root] [--port N]')
        else:
            print(f"missing dashboard dependency ({exc.name}); pip install fastapi jinja2 uvicorn")
        return 1

    parser = argparse.ArgumentParser(description="Open the local OAOS2 dashboard")
    parser.add_argument("runs_root", nargs="?", type=Path, default=Path("runs"))
    parser.add_argument("--port", type=int, default=8722)
    args = parser.parse_args(argv)
    runs_root, port = args.runs_root, args.port
    if not runs_root.exists():
        print(f"no runs directory at {runs_root}")
        return 1
    print(f"oaos2 dashboard on http://127.0.0.1:{port} — runs root: {runs_root}")
    uvicorn.run(create_app(runs_root), host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
