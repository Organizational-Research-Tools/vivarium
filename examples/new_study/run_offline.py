"""A new study on the materials workshop, offline: two presets that differ in one setting, checked, compared and
run with scripted laboratories. No model is called and nothing is spent.

  uv run python examples/new_study/run_offline.py            # check, compare, and run both arms
  uv run python examples/new_study/run_offline.py --no-run   # check and compare only
  uv run python examples/new_study/run_offline.py --arms <control> <treatment>   # a study of your own

The study asks whether the reason a formal rule gives matters. Its control arm is the competition study's
competitive arm (`competition_competitive`); its treatment arm, `example_rule_injury`, names that preset as its
base and changes one setting, `rule_level`, so the industry association's request gives the injury reason instead
of the approved-list reason. See README.md in this folder.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO), str(HERE.parent)]

from oaos2.organizations.compare import describe, preset_differences  # noqa: E402
from oaos2.organizations.loader import load_org_spec  # noqa: E402
from oaos2.trace.invariants import load_all_events  # noqa: E402
from quickstart import run, shown  # noqa: E402

ARMS = ("competition_competitive", "example_rule_injury")


def check(arms=ARMS) -> None:
    """Load both arms as a run would, and show that a misspelled setting is refused by name."""
    for name in arms:
        spec = load_org_spec(name)
        print(f"{name}: loads ({spec.n_agents} laboratories; bases: "
              f"{', '.join(p.stem for p in spec.base_refs) or 'none'})")
    spec = load_org_spec(arms[1])
    typo = dataclasses.replace(spec, live_coordination={**spec.live_coordination, "rule_levle": "injury"})
    try:
        typo.validate()
    except ValueError as exc:
        print(f"a misspelled setting is refused before any run: {exc}")


def compare(arms=ARMS) -> list[dict]:
    diffs = preset_differences(*arms)
    print(f"\n{arms[0]} and {arms[1]} differ in {len(diffs)} setting(s):")
    for d in diffs:
        print(describe(d))
    return diffs


def rule_sentence(run_dir: Path) -> str:
    """The supplier-list paragraph the run's laboratories were given, as the event record holds it."""
    for e in load_all_events(run_dir):
        text = json.dumps(e.get("payload") or {})
        at = text.find("Supplier list.")
        if at >= 0:
            return json.loads('"' + text[at:].split('"', 1)[0] + '"').split("The client", 1)[0].strip()
    return "(not found)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-run", action="store_true", help="check and compare only")
    ap.add_argument("--arms", nargs=2, default=list(ARMS), metavar=("CONTROL", "TREATMENT"),
                    help="the two presets to check, compare and run (default: this example's)")
    ap.add_argument("--runs-root", type=Path, default=REPO / "examples" / "runs")
    args = ap.parse_args()
    arms = tuple(args.arms)
    check(arms)
    compare(arms)
    if args.no_run:
        return 0
    args.runs_root.mkdir(parents=True, exist_ok=True)
    print("\nrunning each arm offline (six scripted laboratories, a 15-second deadline):")
    for name in arms:
        result = asyncio.run(run(None, args.runs_root, preset=name, experiment_id="new_study"))
        print(f"{name}: archive {shown(result.run_dir)}; closed: {result.closed}; valid: {result.archive_valid}")
        print(f"  the laboratories read: {rule_sentence(Path(result.run_dir))}")
    print(f"\nnext: uv run python scripts/dashboard.py {shown(args.runs_root)} --port 8722")
    return 0


if __name__ == "__main__":
    sys.exit(main())
