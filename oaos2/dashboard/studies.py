"""Declared membership of run lineages in studies (DASHBOARD.md §4.1).

One-off launchers name a fresh experiment per run, so a study's pilots land in many
single-run lineages. ``library/studies.yaml`` lets the researcher declare which lineages
belong together. The dashboard only groups its index by it; membership is never inferred
from a name the file does not list, and nothing outside the dashboard reads the file."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

import yaml


def load_studies(path: Path) -> list[dict]:
    """The declared studies in file order; a missing file declares none.

    A malformed entry raises: a silent skip would quietly regroup the archive."""
    if not Path(path).exists():
        return []
    data = yaml.safe_load(Path(path).read_text()) or {}
    out, seen = [], set()
    for entry in data.get("studies") or []:
        study_id, patterns = entry.get("id"), entry.get("lineages")
        if not isinstance(study_id, str) or not study_id or study_id in seen:
            raise ValueError(f"studies.yaml: each study needs a unique id, got {study_id!r}")
        if not isinstance(patterns, list) or not all(isinstance(p, str) and p for p in patterns):
            raise ValueError(f"studies.yaml: study {study_id!r} needs a list of lineage patterns")
        seen.add(study_id)
        out.append({"id": study_id, "title": entry.get("title") or study_id,
                    "record": entry.get("record"), "lineages": list(patterns)})
    return out


def study_of(lineage: str | None, studies: list[dict]) -> dict | None:
    """The first declared study one of whose patterns matches this lineage."""
    if not lineage:
        return None
    for study in studies:
        if any(fnmatchcase(lineage, pattern) for pattern in study["lineages"]):
            return study
    return None
