"""Ordered event recording, schemas, retention settings, and archive checks.

RunSpine accepts events through one durable queue and writer per run. Events share
a sequence across experiment and infrastructure streams. Schema definitions
supply common fields; registries supply accepted event names. Finalization checks
ordering, dependencies, accounting, and the permitted terminal-record shape."""

from oaos2.trace.schema import (
    AUDIENCES,
    CHANNELS,
    PHASE_CLASSES,
    SCHEMA_VERSION,
    Audience,
    Channel,
    Event,
    PhaseClass,
)

__all__ = [
    "AUDIENCES",
    "CHANNELS",
    "PHASE_CLASSES",
    "SCHEMA_VERSION",
    "Audience",
    "Channel",
    "Event",
    "PhaseClass",
]
