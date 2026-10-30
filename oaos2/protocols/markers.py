"""Extract marked handoff text, with an optional retry and recorded failure.

parse_markers() selects the first configured marker found in the narration.
extract_handoff() can ask a supplied callback to retry; success after retries
or an injected failure placeholder produces intervention links. The helper is
unit-tested but is not used by current live pipelines, which transfer already
submitted payloads. Policy fields for prompt wording and early stopping need
caller support; declaring them does not alter a model loop."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable


@dataclass
class MarkerPolicy:
    required_markers: list[str] = field(default_factory=lambda: ["handoff"])
    max_retries: int = 2
    on_exhaustion: str = "inject_handoff_failure_stub"
    early_break_on_marker: bool = True  # caller-side early-stop setting; not applied by this helper
    marker_immediacy_instruction: str | None = None  # optional prompt instruction for the caller


@dataclass
class MarkerExtraction:
    payload: str | None
    is_stub: bool
    intervention_event_ids: list[str]
    last_event_id: str


def parse_markers(narration: str, markers: list[str]) -> str | None:
    """Return the content inside the first required marker, or None if absent."""
    for marker in markers:
        m = re.search(rf"<{marker}>(.*?)</{marker}>", narration, re.DOTALL)
        if m:
            return m.group(1).strip()
    return None


async def extract_handoff(
    *,
    narration: str,
    policy: MarkerPolicy,
    spine,
    agent_id: str,
    turn_id: str,
    caused_by: str,
    retry_fn: Callable[[str], Awaitable[tuple[str, str]]] | None = None,
) -> MarkerExtraction:
    """Extract a handoff payload from narration; retry, then stub (M6 §2).

    ``retry_fn(correction) -> (new_narration, new_event_id)`` performs a real
    model retry (cost attributed to ``retry_after_validation``). If omitted,
    retries are skipped (straight to the stub) — useful for deterministic tests.
    """
    payload = parse_markers(narration, policy.required_markers)
    if payload is not None:
        return MarkerExtraction(payload=payload, is_stub=False, intervention_event_ids=[], last_event_id=caused_by)

    prev = caused_by
    if retry_fn is not None:
        for attempt in range(policy.max_retries):
            narration, prev = await retry_fn(
                f"Emit the required marker(s) now: {policy.required_markers}"
            )
            payload = parse_markers(narration, policy.required_markers)
            if payload is not None:
                iv = await spine.emit_event(
                    "intervention.recorded", agent_id=agent_id, turn_id=turn_id, caused_by=prev,
                    payload={"kind": "marker_retry", "class": "recorded", "attempts": attempt + 1},
                )
                return MarkerExtraction(payload=payload, is_stub=False,
                                        intervention_event_ids=[iv], last_event_id=iv)

    # Exhausted → loud failure stub (a recorded intervention; never silent).
    failed = await spine.emit_event(
        "handoff_extraction_failed", agent_id=agent_id, turn_id=turn_id, caused_by=prev,
        payload={"role": agent_id},
    )
    stub = "<oaos-handoff-failure reason='markers_missing'/>"
    injected = await spine.emit_event(
        "handoff_stub_injected", agent_id=agent_id, turn_id=turn_id, caused_by=failed,
        payload={"stub": stub, "intervention_class": "recorded"},
    )
    iv = await spine.emit_event(
        "intervention.recorded", agent_id=agent_id, turn_id=turn_id, caused_by=injected,
        payload={"kind": "handoff_stub", "class": "recorded"},
    )
    return MarkerExtraction(payload=stub, is_stub=True, intervention_event_ids=[iv], last_event_id=iv)
