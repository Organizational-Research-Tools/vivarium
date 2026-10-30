"""Store researcher interpretations separately from the original event record.

LabelRegistry validates label definitions; AnnotationLinkWriter appends links
between labels and events under annotations/<namespace>.jsonl. A namespace
groups one vocabulary of labels. Automatic classifiers are separate extensions;
recording a label does not establish that its interpretation is reliable."""

from oaos2.annotations.label_registry import (
    InvalidAnnotation,
    LabelRegistry,
    LabelSchema,
    UnknownLabelSchema,
    validate_annotation_link,
)
from oaos2.annotations.link_writer import AnnotationLinkWriter, load_links

__all__ = [
    "LabelRegistry",
    "LabelSchema",
    "InvalidAnnotation",
    "UnknownLabelSchema",
    "validate_annotation_link",
    "AnnotationLinkWriter",
    "load_links",
]
