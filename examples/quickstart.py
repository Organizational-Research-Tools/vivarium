"""Vivarium quickstart: one offline run of the materials lab, then the dashboard on its archive.

No model is called, no container is started, and nothing is spent. Scripted stand-in laboratories
(`tests/tasks/test_materials_lab_pack.py`) act through the lab's real tools. The platform runs them exactly
as it runs model agents: the same agent loop, permission checks, simulated containers (`FakeContainerBackend`)
and event record. The run's archive goes to `examples/runs/`.

  uv run python examples/quickstart.py            # three labs qualify one recipe for the client
  uv run python examples/quickstart.py --study    # the competition study's six-lab competitive preset
  uv run python examples/quickstart.py --study cooperative
  uv run python examples/quickstart.py --preset <your preset>   # any preset, its laboratories scripted to read and wait
  uv run python scripts/dashboard.py examples/runs --port 8722

By default the preset is `materials_trio`: three laboratories, each owning one test instrument. One registers
a recipe, grants the others access, measures a panel on its own instrument and asks for the other two; they
measure and share their receipts; it then files a report citing all three, which the client accepts and
credits. With `--study` the preset is `competition_competitive` (or, with `--study cooperative`,
`competition_cooperative`): the materials workshop with the competition study's credit institution, which
resolves to the preset its main study ran. Six laboratories read what the study's laboratories were given
(their situation, their records, the reports, the board) and wait out a 15-second deadline; nothing is
qualified. `scripts/compare_presets.py competition_competitive competition_cooperative` lists where the two
arms differ before any run; `examples/new_study/` builds a study of its own on the same base.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from oaos2.docker.backend import FakeContainerBackend  # noqa: E402
from oaos2.experiments.runner import run_org_live  # noqa: E402
from oaos2.organizations.loader import load_org_spec  # noqa: E402
from oaos2.trace.invariants import load_all_events  # noqa: E402
from tests.scripted_stub import _FAKE_DIGEST, _tool  # noqa: E402
from tests.tasks.test_materials_lab_pack import HONEST, _honest_scripts, _ReactiveStub  # noqa: E402


def shown(path) -> str:
    """A path to print: relative to the current directory when it is inside it, quoted for the shell."""
    try:
        return f"'{Path(path).resolve().relative_to(Path.cwd().resolve())}'"
    except ValueError:
        return f"'{path}'"


def reader(results):
    """A laboratory that reads its situation, its records, the reports and the board, then waits for the
    deadline (the study's laboratories have no tool to leave early)."""
    steps = ["lab_info", "my_records", "read_reports", "read_board"]
    n = len(results)
    return _tool(steps[n], "x") if n < len(steps) else _tool("wait", "x")


async def run(study: str | None, runs_root: Path, preset: str | None = None, experiment_id: str = "quickstart"):
    """One offline run: the trio's honest recipe, or (``study`` or ``preset``) six reading laboratories."""
    if study or preset:
        org = load_org_spec(preset or f"competition_{study}")
        lc = dict(org.live_coordination or {})
        # a short offline run: the study's own bounds are for 50-minute model runs
        lc["bounds"] = {**dict(lc.get("bounds") or {}), "wait_s": 5, "drain_s": 1, "assessment_s": 1,
                        "observation_s": 1, "participant_deadline_s": 15}
        org = dataclasses.replace(org, live_coordination=lc)
        stubs = {r.role_id: _ReactiveStub([reader]) for r in org.roles}
    else:
        org = load_org_spec("materials_trio")
        scripts = _honest_scripts(HONEST)
        stubs = {r.role_id: _ReactiveStub(scripts[r.role_id]) for r in org.roles}
    for r in org.roles:
        r.context_budget_tokens = None  # a scripted laboratory cannot write a summary of its own context
    order = iter([stubs[r.role_id] for r in org.roles])
    return await run_org_live(
        org, runs_root, tier="main", model_ref="stub/deterministic", experiment_id=experiment_id,
        task_pack="materials_lab", reasoning_kind="none", cap_usd=5.0, max_model_calls=200,
        backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=lambda: next(order))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--study", nargs="?", const="competitive", choices=["competitive", "cooperative"],
                    help="the competition study's arm, as the workshop plus its credit institution (default competitive)")
    ap.add_argument("--preset", default=None,
                    help="any preset id in library/organizations/ (a study of your own), run offline by scripted "
                         "laboratories that read their situation and wait out a 15-second deadline")
    ap.add_argument("--runs-root", type=Path, default=REPO / "examples" / "runs")
    args = ap.parse_args()
    args.runs_root.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run(args.study, args.runs_root, preset=args.preset))
    events = load_all_events(result.run_dir)
    count = lambda cls: sum(e["event_class"] == cls for e in events)  # noqa: E731
    status = json.loads((Path(result.run_dir) / "run_status.json").read_text())
    print(f"archive: {shown(result.run_dir)}")
    print(f"preset: {status.get('preset_id')}; events recorded: {len(events)}; tool calls: {count('tool.called')}")
    print(f"reports filed: {count('report.submitted')}; scored by the client: {count('report.scored')}; "
          f"credits awarded: {count('credit.awarded')}")
    print(f"closed: {result.closed}; archive valid: {result.archive_valid}; laboratories that stopped with an error: "
          f"{count('agent.failed')}")
    print(f"next: uv run python scripts/dashboard.py {shown(args.runs_root)} --port 8722, then open http://127.0.0.1:8722")
    return 0


if __name__ == "__main__":
    sys.exit(main())
