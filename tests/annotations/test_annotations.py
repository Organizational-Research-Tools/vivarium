"""Annotation substrate (DESIGN §16): label registry + link writer, arity-validated,
namespace-sharded, append-only over the trace."""

from __future__ import annotations

import pytest

from oaos2.annotations import (
    AnnotationLinkWriter,
    InvalidAnnotation,
    LabelRegistry,
    LabelSchema,
    UnknownLabelSchema,
    load_links,
    validate_annotation_link,
)
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.records import AnnotationLink


def _unary(**kw):
    base = dict(link_id="l1", label_schema_ref="attention/focus", namespace="attention",
                arity="unary", event_ids=["e1"], label={"focus": "spec"})
    base.update(kw)
    return AnnotationLink(**base)


def test_arity_rules_validate_without_registry() -> None:
    validate_annotation_link(_unary())  # ok
    with pytest.raises(InvalidAnnotation):
        validate_annotation_link(_unary(event_ids=["e1", "e2"]))  # unary must span 1
    with pytest.raises(InvalidAnnotation):
        validate_annotation_link(_unary(arity="relational", relation_kind=None, event_ids=["e1", "e2"]))
    # relational needs ≥2 events + relation_kind
    validate_annotation_link(_unary(arity="relational", relation_kind="imitates", event_ids=["e1", "e2"]))
    with pytest.raises(InvalidAnnotation):
        validate_annotation_link(_unary(classifier_mode="bogus"))


def test_registry_validates_ref_and_arity() -> None:
    reg = LabelRegistry()
    with pytest.raises(UnknownLabelSchema):
        validate_annotation_link(_unary(), registry=reg)  # nothing registered yet
    reg.register(LabelSchema("attention/focus", namespace="attention", arity="unary"))
    validate_annotation_link(_unary(), registry=reg)  # now ok
    # arity mismatch between link and schema is rejected.
    with pytest.raises(InvalidAnnotation):
        validate_annotation_link(_unary(arity="group"), registry=reg)
    # relational schema needs a relation_kind at declaration time.
    with pytest.raises(InvalidAnnotation):
        LabelSchema("x", namespace="n", arity="relational")
    with pytest.raises(InvalidAnnotation):
        reg.register(LabelSchema("attention/focus", namespace="attention", arity="unary"))  # dup


def test_writer_shards_by_namespace_and_round_trips(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "r")
    reg = LabelRegistry()
    reg.register(LabelSchema("attention/focus", namespace="attention", arity="unary"))
    reg.register(LabelSchema("relay/suspected", namespace="relay", arity="relational",
                             relation_kind="suspected_semantic_relay"))
    w = AnnotationLinkWriter(rd.root, registry=reg)
    w.write(_unary())
    w.write(_unary(link_id="l2", label={"focus": "data"}))
    w.write(AnnotationLink(link_id="l3", label_schema_ref="relay/suspected", namespace="relay",
                           arity="relational", relation_kind="suspected_semantic_relay",
                           event_ids=["e9", "e10"], classifier_mode="pattern"))
    # sharded by namespace
    assert (rd.annotations / "attention.jsonl").exists() and (rd.annotations / "relay.jsonl").exists()
    assert len(load_links(rd.root, namespace="attention")) == 2
    assert len(load_links(rd.root)) == 3  # all namespaces
    # an unregistered ref is refused at write time (never lands).
    with pytest.raises(UnknownLabelSchema):
        w.write(_unary(link_id="l4", label_schema_ref="frame/unknown", namespace="frame"))


def test_writer_rejects_unsafe_namespace(tmp_path) -> None:
    # A namespace must be a plain slug — never a path that could escape the annotations
    # slot and append into the immutable trace (the module promises it never mutates the spine).
    rd = RunDir.create(tmp_path, "e", "p", "r")
    w = AnnotationLinkWriter(rd.root)  # no registry → arity/namespace checks only
    for bad in ("../../trace/events", "a/b", "..", "."):
        with pytest.raises(InvalidAnnotation):
            w.write(_unary(label_schema_ref="x", namespace=bad))
