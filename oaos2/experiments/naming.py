"""Run-archive naming conventions (DESIGN §17.3).

The run path is ``runs/{experiment_id}/{task_pack_id}/{run_id}/``. To keep folders
legible at a glance (and unique per run so re-runs/replications never clobber),
``run_id`` encodes the cell's key factors — org preset, difficulty, model — plus a
replication index and a ULID. The ``config/resolved.json`` snapshot remains the
authoritative full record; these names are for human navigation.
"""

from __future__ import annotations

import re

from oaos2.ulid import new_ulid


def _slug(s: str) -> str:
    """Filesystem-friendly slug: lowercase, '/'→'-', non-alnum→'_', collapse repeats."""
    s = s.lower().replace("/", "-")
    s = re.sub(r"[^a-z0-9._-]+", "_", s).strip("_-")
    return re.sub(r"_+", "_", s)


def experiment_dir_name(design_name: str) -> str:
    """Legible experiment_id from a design name (dots→underscores for the path)."""
    return _slug(design_name.replace(".", "_"))


def run_id(*, preset: str, difficulty: str, model_ref: str, rep: int,
           variant: str | None = None) -> str:
    """Unique, legible run_id: ``{preset}__{difficulty}__{model}[__{variant}]__rep{NN}__{ulid}``.

    ``variant`` names a swept apparatus variant (e.g. a clock horizon ``r36``)
    so distinct-variant archives are legible at a glance; the ULID already
    guarantees uniqueness either way.
    """
    mid = f"__{_slug(variant)}" if variant else ""
    return (f"{_slug(preset)}__{_slug(difficulty)}__{_slug(model_ref)}"
            f"{mid}__rep{rep:02d}__{new_ulid()}")
