"""The competition study's frozen files in this release match the pin manifest written at the freeze
(library/experiments/evidence/pc1_9_2_pins.json): the preregistration, the coding documents, the two presets the
study ran, the readout's scripts (kept in data/competition-9.2/analysis/study_scripts/), and the plan apart from
its launch fields."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PINS = json.loads((REPO / "library" / "experiments" / "evidence" / "pc1_9_2_pins.json").read_text())
STUDY_SCRIPTS = REPO / "data" / "competition-9.2" / "analysis" / "study_scripts"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _released(pinned: str) -> Path | None:
    """Where the release keeps a pinned file, or None when it does not carry it."""
    if (REPO / pinned).is_file() and not pinned.startswith(("oaos2/", "scripts/")):
        return REPO / pinned
    if pinned.startswith("scripts/") and (STUDY_SCRIPTS / Path(pinned).name).is_file():
        return STUDY_SCRIPTS / Path(pinned).name
    return None


def test_every_pinned_file_the_release_carries_matches_the_manifest():
    carried = {p: _released(p) for p in PINS["files"]}
    checked = {p: q for p, q in carried.items() if q is not None}
    assert {"docs/experiments/pc1_prereg_9_2.md", "library/organizations/pc1_supplier_g_xmodel7.yaml",
            "library/organizations/pc1_supplier_g_xmodel7_cooperative.yaml", "docs/experiments/pc1_codebook.md",
            "scripts/pc1_readout_x7b.py"} <= set(checked)
    for pinned, path in checked.items():
        assert _sha(path) == PINS["files"][pinned].removeprefix("sha256:"), pinned


def test_the_plan_is_the_frozen_plan_apart_from_its_launch_fields():
    plan = yaml.safe_load((REPO / PINS["plan"]).read_text())
    body = {k: v for k, v in plan.items() if k not in PINS["launch_fields"]}
    assert hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest() == \
        PINS["plan_sha256_without_launch_fields"].removeprefix("sha256:")
    assert plan["frozen_commit"] == "7d63a96d2cdb495e7e76437dbea4cdb9655cd2e7"


def test_a_plan_cell_becomes_the_launcher_command_the_batch_built():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_plan_cell", REPO / "scripts" / "run_plan_cell.py")
    cell = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cell)
    plan = yaml.safe_load((REPO / PINS["plan"]).read_text())
    args = cell.cell_args(plan, "glm53", "competitive", 41)
    assert args[:6] == ["--preset", "pc1_supplier_g_xmodel7", "--seed", "41", "--model", "openrouter/z-ai/glm-5.3-flash@z-ai"]
    assert args[args.index("--guard-rate") + 1] == "0.017" and args[args.index("--calls") + 1] == "1500"
    assert args[-2:] == ["--experiment", "pc1_x7b_glm53_competitive_s41"]
