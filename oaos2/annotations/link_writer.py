"""Append researcher annotations under annotations/<namespace>.jsonl.

Check link structure, and schema membership when a registry is supplied, then
validate that the namespace is safe to use as a filename. The writer does not
check whether referenced event IDs exist. Dashboard callers provide additional
checks. These annotations are separate research data; they are not disposable
views that can necessarily be rebuilt from the event log."""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.annotations.label_registry import (
    InvalidAnnotation,
    LabelRegistry,
    validate_annotation_link,
)


class AnnotationLinkWriter:
    """Append validated ``AnnotationLink`` records to ``<run>/annotations/<namespace>.jsonl``."""

    def __init__(self, run_dir: Path, *, registry: LabelRegistry | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.registry = registry
        self.dir = self.run_dir / "annotations"

    def write(self, link) -> Path:
        """Validate then append one link to its namespace shard; returns the shard path."""
        validate_annotation_link(link, registry=self.registry)
        # The namespace becomes a filename shard — it must be a plain slug, never a path.
        # Otherwise `namespace="../../trace/events"` would escape the annotations slot and
        # could append into the immutable trace dir (this module promises it never does).
        ns = link.namespace
        if not ns or "/" in ns or "\\" in ns or ns in (".", "..") or ns.startswith("."):
            raise InvalidAnnotation(f"unsafe annotation namespace {ns!r} (must be a plain slug)")
        self.dir.mkdir(parents=True, exist_ok=True)
        shard = self.dir / f"{ns}.jsonl"
        with shard.open("a") as f:
            f.write(json.dumps(link.model_dump(), sort_keys=True) + "\n")
        return shard


def load_links(run_dir: Path, *, namespace: str | None = None) -> list[dict]:
    """Read back annotation links from a run (all namespaces, or one shard)."""
    adir = Path(run_dir) / "annotations"
    if not adir.exists():
        return []
    shards = ([adir / f"{namespace}.jsonl"] if namespace
              else sorted(adir.glob("*.jsonl")))
    out: list[dict] = []
    for shard in shards:
        if shard.exists():
            out += [json.loads(line) for line in shard.read_text().splitlines() if line.strip()]
    return out
