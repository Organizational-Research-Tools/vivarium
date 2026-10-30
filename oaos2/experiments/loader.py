"""Read a library experiment YAML file into an ExperimentDesign.

The runner expands the resulting factors into cells. YAML supports combinations
of existing capabilities; a new mechanism can still require an implementation.
Only fields consumed by this loader become design settings. A comment or an
unknown field does not activate a control."""

from __future__ import annotations

from pathlib import Path

import yaml

from oaos2.experiments.design import ExperimentDesign, ParityPolicy
from oaos2.library import library_dir


def _design_path(name: str) -> Path:
    return library_dir() / "experiments" / f"{name}.yaml"  # resolved at call time


def validate_final_preregistration(ref: str | Path, *, root: Path | None = None) -> Path:
    """Resolve a preregistration and require its explicit, machine-readable final status.

    Existence alone is not a confirmatory gate: a design could point at a draft full of
    provisional decisions and still launch. The status declaration is intentionally
    simple Markdown (``STATUS: FINAL`` on its own line, with optional quote/header/bold
    markup) so both humans and the runtime read the same artifact.
    """
    path = Path(ref)
    if not path.is_absolute():
        path = (root or Path(__file__).resolve().parents[2]) / path
    if not path.is_file():
        raise FileNotFoundError(
            f"preregistration_ref does not exist: {ref} (resolved to {path})")
    # A status declaration belongs in the document header. Do not accept an incidental
    # ``STATUS: FINAL`` example or historical note deep in an otherwise draft document.
    for raw in path.read_text().splitlines()[:20]:
        status = raw.strip().lstrip(">").strip().lstrip("#").strip()
        status = status.replace("**", "").replace("__", "").strip().casefold()
        if status == "status: final":
            return path
    raise ValueError(
        f"confirmatory preregistration must declare `STATUS: FINAL` on its own line: {ref}")


def load_design(name: str) -> ExperimentDesign:
    path = _design_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"no experiment design {name!r} at {path}")
    m = yaml.safe_load(path.read_text())
    pp = m.get("parity_policy", {}) or {}
    design = ExperimentDesign(
        name=m.get("name", name),
        task_pack=m.get("task_pack", "paper_replication"),
        factors=dict(m.get("factors", {})),
        replications=int(m.get("replications", 1)),
        mode=m.get("mode", "pilot"),
        parity_policy=ParityPolicy(
            basis=pp.get("basis", "usd"), regime=pp.get("regime", "both"),
            cap_usd=(float(pp["cap_usd"]) if pp.get("cap_usd") is not None else None),
            cap_tokens=(int(pp["cap_tokens"]) if pp.get("cap_tokens") is not None else None),
            reserve_tokens=int(pp.get("reserve_tokens", 20000)),
        ),
        platform_seed=int(m.get("platform_seed", 0)),
        preregistration_ref=m.get("preregistration_ref"),
        # Readiness evidence is design data too (estimand-correction review
        # 2026-08-27): the FINAL executable design declares its hash-pinned
        # capacity artifacts and per-tier expected verdicts in YAML.
        confirmatory_evidence=dict(m.get("confirmatory_evidence", {}) or {}),
        source_ref=path,
    )
    design.validate()  # confirmatory requires a preregistration_ref to be SET (§19)
    # ...and for confirmatory, that the referenced preregistration is explicitly FINAL —
    # existence alone admits a draft with unresolved apparatus choices (§19).
    # Refs are repo-relative (e.g. "library/experiments/…md"); the repo root is the
    # library's parent.
    if design.mode == "confirmatory" and design.preregistration_ref:
        validate_final_preregistration(design.preregistration_ref, root=library_dir().parent)
    return design


def available_designs() -> list[str]:
    d = library_dir() / "experiments"
    return sorted(p.stem for p in d.glob("*.yaml")) if d.is_dir() else []
