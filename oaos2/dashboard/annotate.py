"""Append researcher-supplied annotations separately from the trace.

Label schemas come from task codebooks and the dashboard's schema file. The
AnnotationLinkWriter validates structure and appends namespace-sharded records.
This endpoint stamps classifier_mode="deferred" and defaults label.coder to
"human"; metadata is not evidence of an independent human judgment. There is no
dashboard deletion or replacement action. Coding records need their own
preservation and correction rules.
"""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.annotations.label_registry import LabelRegistry, LabelSchema
from oaos2.annotations.link_writer import AnnotationLinkWriter, load_links
from oaos2.trace.records import AnnotationLink
from oaos2.ulid import new_ulid


def _schemas_path(runs_root: Path) -> Path:
    return Path(runs_root) / ".dashboard" / "label_schemas.json"


def researcher_schemas(runs_root: Path) -> list[LabelSchema]:
    """The researcher's own lenses (``<runs_root>/.dashboard/label_schemas.json``)."""
    path = _schemas_path(runs_root)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    out = []
    for d in raw:
        try:
            out.append(LabelSchema(**d))  # re-validated on every load (arity contract)
        except Exception:
            continue  # a hand-edited bad entry must not take the page down
    return out


def codebook_entries() -> dict[str, dict]:
    """``ref → codebook entry`` over every pack codebook in the library (Track B)."""
    from oaos2.annotations.codebook import load_all_codebooks
    out: dict[str, dict] = {}
    for book in load_all_codebooks():
        for code in book["codes"]:
            out.setdefault(code["ref"], code)  # first pack wins a collision; the page flags it
    return out


def load_schemas(runs_root: Path) -> list[LabelSchema]:
    """Every lens the dashboard may code with: the pack codebooks (versioned,
    committed) first, then the researcher's file — a ref defined in both keeps
    the codebook's definition."""
    seen: dict[str, LabelSchema] = {}
    for code in codebook_entries().values():
        seen[code["ref"]] = code["schema"]
    for schema in researcher_schemas(runs_root):
        seen.setdefault(schema.label_schema_ref, schema)
    return list(seen.values())


def save_schema(runs_root: Path, schema: LabelSchema) -> None:
    """Add one lens; ref collisions are an error (same rule as LabelRegistry)."""
    if any(s.label_schema_ref == schema.label_schema_ref for s in load_schemas(runs_root)):
        raise ValueError(f"label schema {schema.label_schema_ref!r} already exists")
    schemas = researcher_schemas(runs_root) + [schema]
    path = _schemas_path(runs_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([s.__dict__ for s in schemas], indent=2, sort_keys=True) + "\n")


def registry_for(runs_root: Path) -> LabelRegistry:
    reg = LabelRegistry()
    for s in load_schemas(runs_root):
        reg.register(s)
    return reg


def write_link(runs_root: Path, run_dir: Path, *, label_schema_ref: str,
               event_ids: list[str], note: str = "", extra: dict | None = None) -> AnnotationLink:
    """Validate and append a supplied label. ``extra`` carries reading metadata.
    This function does not check note text against hidden keys; dashboard routes
    apply their own text and event-reference checks before calling it."""
    schemas = {s.label_schema_ref: s for s in load_schemas(runs_root)}
    schema = schemas.get(label_schema_ref)
    if schema is None:
        raise ValueError(f"unknown label schema {label_schema_ref!r}")
    label = {"note": note, "coder": "human"}
    for k, v in (extra or {}).items():
        if v not in (None, ""):
            label[k] = v
    code = codebook_entries().get(label_schema_ref)
    if code is not None:  # a codebook lens: the link says which definition it was coded under
        label["codebook_sha256"] = code["codebook_sha256"]
        label["origin"] = code["origin"]
    link = AnnotationLink(
        link_id=new_ulid(),
        label_schema_ref=schema.label_schema_ref,
        namespace=schema.namespace,
        arity=schema.arity,
        event_ids=event_ids,
        relation_kind=schema.relation_kind,
        label=label,
        classifier_mode="deferred",  # classifiers are Tier-C; this is hand-coding
    )
    AnnotationLinkWriter(run_dir, registry=registry_for(runs_root)).write(link)
    return link


def links_for_run(run_dir: Path, namespace: str | None = None) -> list[dict]:
    return load_links(run_dir, namespace=namespace)


def links_by_event(run_dir: Path) -> dict[str, list[dict]]:
    """event_id → links citing it (the explorer's margin marks)."""
    out: dict[str, list[dict]] = {}
    for link in load_links(run_dir):
        for eid in link.get("event_ids") or []:
            out.setdefault(eid, []).append(link)
    return out
