"""Validate annotation structure and optionally check a registered label schema.

Check classifier mode, the number of referenced events, and the presence of a
relation kind for relational links. With a registry, require a known schema
and matching arity (one event, relation, or group). This function does not
validate label dictionary contents or verify that event IDs exist in a run."""

from __future__ import annotations

from dataclasses import dataclass

_ARITIES = frozenset({"unary", "relational", "group"})
_CLASSIFIER_MODES = frozenset({"pattern", "plugin", "llm_judge", "deferred"})


class UnknownLabelSchema(Exception):
    """An AnnotationLink references a label schema not in the registry (§16)."""


class InvalidAnnotation(Exception):
    """An AnnotationLink violates its arity/relation/classifier contract (§16)."""


@dataclass(frozen=True)
class LabelSchema:
    """A declared analytic lens. ``arity`` fixes how many events a link spans; a
    ``relational`` schema names its ``relation_kind`` (e.g. ``imitates``)."""

    label_schema_ref: str
    namespace: str
    arity: str  # unary | relational | group
    relation_kind: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.arity not in _ARITIES:
            raise InvalidAnnotation(f"arity {self.arity!r} not in {sorted(_ARITIES)}")
        if self.arity == "relational" and not self.relation_kind:
            raise InvalidAnnotation("a relational label schema must declare a relation_kind")


class LabelRegistry:
    """Open registry of label schemas; redefining a ref is an error unless ``override``."""

    def __init__(self) -> None:
        self._schemas: dict[str, LabelSchema] = {}

    def register(self, schema: LabelSchema, *, override: bool = False) -> None:
        if schema.label_schema_ref in self._schemas and not override:
            raise InvalidAnnotation(
                f"label schema {schema.label_schema_ref!r} already registered (pass override=True)"
            )
        self._schemas[schema.label_schema_ref] = schema

    def get(self, ref: str) -> LabelSchema | None:
        return self._schemas.get(ref)

    def __contains__(self, ref: str) -> bool:
        return ref in self._schemas


def validate_annotation_link(link, *, registry: LabelRegistry | None = None) -> None:
    """Validate an ``AnnotationLink`` against the arity contract (and the registry, if given).

    Arity-independent of any registry: ``unary`` spans exactly one event, ``relational``
    needs ``relation_kind`` + ≥2 events, ``group`` needs ≥1. With a registry, the link's
    ``label_schema_ref`` must be registered and its arity must match the schema's.
    """
    if link.classifier_mode not in _CLASSIFIER_MODES:
        raise InvalidAnnotation(f"classifier_mode {link.classifier_mode!r} not in {sorted(_CLASSIFIER_MODES)}")
    if link.arity not in _ARITIES:
        raise InvalidAnnotation(f"arity {link.arity!r} not in {sorted(_ARITIES)}")
    n = len(link.event_ids)
    if link.arity == "unary" and n != 1:
        raise InvalidAnnotation(f"unary annotation must span exactly 1 event (got {n})")
    if link.arity == "relational":
        if not link.relation_kind:
            raise InvalidAnnotation("relational annotation must set relation_kind")
        if n < 2:
            raise InvalidAnnotation(f"relational annotation must span ≥2 events (got {n})")
    if link.arity == "group" and n < 1:
        raise InvalidAnnotation("group annotation must span ≥1 event")
    if registry is not None:
        schema = registry.get(link.label_schema_ref)
        if schema is None:
            raise UnknownLabelSchema(
                f"label schema {link.label_schema_ref!r} not registered (register it on the "
                "pack's LabelRegistry first, §16)"
            )
        if schema.arity != link.arity:
            raise InvalidAnnotation(
                f"link arity {link.arity!r} ≠ schema {schema.label_schema_ref!r} arity {schema.arity!r}"
            )
