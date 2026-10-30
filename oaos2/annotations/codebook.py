"""Codebooks: the researcher's lenses as versioned data (DESIGN §16; Track B).

A label list is not a codebook.  ``library/tasks/<pack>/codebook.yaml`` carries,
per code: an immutable ref (``<ns>.<name>.v<k>``), the namespace and arity the
``LabelRegistry`` needs, a definition with inclusion and exclusion rules, its
origin (inductive from a reading, or deductive from theory with the condition it
is expected under as a predicate over ``design.*`` labels), exemplar citations,
and a change history.  A changed lens is a NEW ref; the old one stays readable.

The dashboard merges every pack codebook with the researcher's own schema file
and stamps the codebook's hash on each link it writes, so a coded excerpt always
says which definition it was coded under.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from oaos2.annotations.label_registry import LabelSchema
from oaos2.library import library_dir

_ORIGINS = frozenset({"inductive", "deductive", "reading", "design"})


class CodebookError(ValueError):
    """A codebook entry violates the contract (missing definition, bad ref, …)."""


def codebook_paths() -> list[Path]:
    tasks = library_dir() / "tasks"
    if not tasks.exists():
        return []
    return sorted(p for p in tasks.glob("*/codebook.yaml") if p.is_file())


def load_codebook(path: Path) -> dict:
    """One codebook: ``{"pack_id", "path", "sha256", "codes": [entry…]}``; every entry
    validated and carrying a ``schema`` (``LabelSchema``) ready for the registry."""
    raw = path.read_bytes()
    doc = yaml.safe_load(raw) or {}
    sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    pack_id = doc.get("pack_id") or path.parent.name
    codes = []
    seen: set[str] = set()
    for entry in doc.get("codes") or []:
        ref = str(entry.get("ref") or "").strip()
        if not ref or "." not in ref or not ref.rsplit(".", 1)[-1].startswith("v"):
            raise CodebookError(f"{path.name}: code ref {ref!r} must look like <ns>.<name>.v<k>")
        if ref in seen:
            raise CodebookError(f"{path.name}: duplicate code ref {ref!r}")
        seen.add(ref)
        if not str(entry.get("definition") or "").strip():
            raise CodebookError(f"{path.name}: code {ref!r} has no definition")
        origin = str(entry.get("origin") or "inductive")
        if origin not in _ORIGINS:
            raise CodebookError(f"{path.name}: code {ref!r} origin {origin!r} not in {sorted(_ORIGINS)}")
        schema = LabelSchema(
            label_schema_ref=ref,
            namespace=str(entry.get("namespace") or ref.split(".", 1)[0]),
            arity=str(entry.get("arity") or "group"),
            relation_kind=entry.get("relation_kind"),
            description=str(entry.get("definition")).strip(),
        )
        codes.append({
            "ref": ref, "schema": schema, "namespace": schema.namespace, "arity": schema.arity,
            "definition": schema.description,
            "include": list(entry.get("include") or []),
            "exclude": list(entry.get("exclude") or []),
            "origin": origin,
            "predicate": dict(entry.get("predicate") or {}),
            "exemplars": list(entry.get("exemplars") or []),
            "history": list(entry.get("history") or []),
            "pack_id": pack_id, "codebook_sha256": sha,
        })
    return {"pack_id": pack_id, "path": path, "sha256": sha, "codes": codes,
            "title": doc.get("title") or f"{pack_id} codebook"}


def load_all_codebooks() -> list[dict]:
    out = []
    for p in codebook_paths():
        try:
            out.append(load_codebook(p))
        except (OSError, yaml.YAMLError, CodebookError) as exc:
            out.append({"pack_id": p.parent.name, "path": p, "sha256": None, "codes": [],
                        "title": f"{p.parent.name} codebook", "error": f"{type(exc).__name__}: {exc}"})
    return out


def predicate_matches(predicate: dict, design_cell: dict) -> bool | None:
    """Does a deductive code's condition hold for a run?  ``predicate`` maps
    ``design.cell.<factor>`` to a value or list of values; None when the code
    declares no predicate."""
    if not predicate:
        return None
    for key, want in predicate.items():
        have = design_cell.get(key)
        if isinstance(want, list):
            if have not in want:
                return False
        elif have != want:
            return False
    return True
