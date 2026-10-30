"""Run one cell of the competition study's main-study plan again: one model, one arm, one seed.

    uv run python scripts/run_plan_cell.py glm53 competitive 41          # print the run's plan and cost guard; spends nothing
    uv run python scripts/run_plan_cell.py glm53 competitive 41 --go     # launch it (paid, billed to your provider key)

The plan (``library/experiments/plans/pc1_main_9_2_plan.yaml``) names, for each model, its provider and launch
arguments (reasoning budget, spending cap, the cap guard's rate), and the arguments every run shared (the rule's
stated reason, the call limit). This script builds the launcher command the study's batch launcher built for a cell,
in the same order, and runs ``scripts/run_materials_lab_smoke.py`` with it: the frozen preset of the arm, the seed,
the model, the plan's arguments, the preregistration and the cell's experiment name. Without ``--go`` the launcher
prints the run's plan and its cost guard and spends nothing.

The batch launcher itself, which ran the cells in a drawn order, two runs of a seed pair at a time, under a
spending ceiling, with health checks between runs, is not part of this release. A cell run here uses the study's
materials and settings on the release's platform code, which is later than the code the study ran from.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "library" / "experiments" / "plans" / "pc1_main_9_2_plan.yaml"
LAUNCHER = REPO / "scripts" / "run_materials_lab_smoke.py"


def cell_args(plan: dict, model_tag: str, arm: str, seed: int) -> list[str]:
    """The launcher arguments of one cell, as the study's batch launcher built them."""
    models = {m["tag"]: m for m in plan["models"]}
    if model_tag not in models:
        raise SystemExit(f"model {model_tag!r} is not in the plan; it names {sorted(models)}")
    if arm not in plan["arms"]:
        raise SystemExit(f"arm {arm!r} is not in the plan; it names {sorted(plan['arms'])}")
    model = models[model_tag]
    if seed not in [int(s) for s in model.get("seeds") or []]:
        raise SystemExit(f"seed {seed} is not among the plan's seeds for {model_tag}")
    name = plan["experiment_template"].format(model=model_tag, arm=arm, seed=seed)
    prereg = ["--preregistration-ref", str(plan["preregistration_ref"])] if plan.get("preregistration_ref") else []
    return ["--preset", plan["arms"][arm], "--seed", str(seed), "--model", model["model_ref"],
            *[str(a) for a in model.get("args") or []], *[str(a) for a in plan.get("common_args") or []],
            *prereg, "--experiment", name]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("model", help="the plan's model tag: glm53, gpt6luna or sonnet46")
    ap.add_argument("arm", help="competitive or cooperative")
    ap.add_argument("seed", type=int)
    ap.add_argument("--plan", type=Path, default=PLAN)
    ap.add_argument("--go", action="store_true", help="launch the run (paid); without it nothing is spent")
    a = ap.parse_args(argv)
    args = cell_args(yaml.safe_load(a.plan.read_text()), a.model, a.arm, a.seed)
    command = [sys.executable, str(LAUNCHER), *args, *(["--go"] if a.go else [])]
    print("launcher:", " ".join(command[1:]))
    return subprocess.run(command, cwd=REPO).returncode


if __name__ == "__main__":
    sys.exit(main())
