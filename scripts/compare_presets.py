"""Show where two organization presets differ, setting by setting, before any run.

    PYTHONPATH="$PWD" python scripts/compare_presets.py <preset a> <preset b> [--check]

A preset is named by its id (``competition_competitive``) or by its file (``library/organizations/....yaml``).

Both presets are read with their bases applied. ``--check`` also loads each one as a run would
(``load_org_spec``), which refuses a setting the task does not know, and exits 1 if either is refused.
Spends nothing and calls no model.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oaos2.organizations.compare import describe, preset_differences  # noqa: E402
from oaos2.organizations.loader import load_org_spec  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("a", help="a preset id, or the path of its file")
    ap.add_argument("b", help="a preset id, or the path of its file")
    ap.add_argument("--check", action="store_true", help="also load both presets as a run would")
    args = ap.parse_args(argv)
    args.a, args.b = (Path(x).stem if x.endswith(".yaml") else x for x in (args.a, args.b))
    if args.check:
        for name in (args.a, args.b):
            try:
                load_org_spec(name)
            except (ValueError, FileNotFoundError) as exc:
                print(f"{name}: refused: {exc}")
                return 1
            print(f"{name}: loads")
    diffs = preset_differences(args.a, args.b)
    print(f"{args.a} and {args.b} differ in {len(diffs)} setting(s)")
    for d in diffs:
        print(describe(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
