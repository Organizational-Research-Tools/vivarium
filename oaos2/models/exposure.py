"""Check what model information the requested adapter declares it can provide.

ModelExposureContract requests reasoning traces or counts, tool-result
visibility, and scratchpad persistence. resolve_exposure compares those requests
with adapter capabilities. Confirmatory mode refuses unsupported requests;
other modes return a result marked exposure_confounded. A reasoning summary
does not satisfy a request for the full exposed trace.

These are declared-capability checks. Actual provider behavior and the fairness
of a model comparison require separate evidence."""

from __future__ import annotations

from dataclasses import dataclass

from oaos2.models.types import ExposureRealized


class ExposureUnsatisfiable(Exception):
    """A requested exposure cannot be produced by the backend (M3 §2.1)."""

    def __init__(self, field_name: str, provider_id: str):
        self.field_name = field_name
        self.provider_id = provider_id
        super().__init__(
            f"exposure {field_name!r} is unsatisfiable on provider {provider_id!r} "
            "(exact-match required; a summary is not the raw trace)"
        )


@dataclass(frozen=True)
class ModelExposureContract:
    thinking_trace_to_agent: bool = False
    reasoning_tokens_to_agent: bool = False
    tool_result_visibility: str = "full"  # full | redacted | none
    scratchpad_persistence: bool = False

    def requested_truthy_fields(self) -> list[str]:
        """The boolean exposures the contract requests be present (must be satisfiable)."""
        out: list[str] = []
        if self.thinking_trace_to_agent:
            out.append("thinking_trace_to_agent")
        if self.reasoning_tokens_to_agent:
            out.append("reasoning_tokens_to_agent")
        if self.scratchpad_persistence:
            out.append("scratchpad_persistence")
        return out


@dataclass
class ExposureResolved:
    contract: ModelExposureContract
    realized: ExposureRealized
    confounded: bool = False


def resolve_exposure(
    contract: ModelExposureContract,
    adapter,
    *,
    confirmatory: bool = True,
    model_ref: str | None = None,
) -> ExposureResolved:
    """Resolve the contract against the adapter's exact-match capabilities (M3 §2.1).

    In ``confirmatory`` mode an unsatisfiable requested exposure raises
    ``ExposureUnsatisfiable`` (the cell is refused at the sweep boundary). Outside
    confirmatory, the cell runs but is stamped ``exposure_confounded`` on the
    realized exposure (so the confound is on the face of the archive).
    """
    # A provider may expose different reasoning surfaces on different models.
    # Older adapters retain their existing declaration.
    model_caps = getattr(adapter, "capabilities_for", None)
    caps = (model_caps(model_ref) if model_caps is not None and model_ref is not None
            else getattr(adapter, "capabilities", None))
    satisfiable = (set(caps.satisfiable_exposures) if model_caps is not None and model_ref is not None
                   else adapter.satisfiable_exposures())
    unmet = [f for f in contract.requested_truthy_fields() if f not in satisfiable]
    confounded = False
    if unmet:
        if confirmatory:
            raise ExposureUnsatisfiable(unmet[0], adapter.provider_id)
        confounded = True

    # tool_result_visibility is a STRING-valued exposure (full|redacted|none), so
    # it is gated against the adapter's supported modes too (M3 §2.1) — previously
    # it was passed through verbatim and effectively assumed always satisfiable.
    supported_visibility = getattr(
        caps,
        "tool_result_visibility_modes",
        frozenset({"full"}),
    )
    visibility_ok = contract.tool_result_visibility in supported_visibility
    if not visibility_ok:
        if confirmatory:
            raise ExposureUnsatisfiable("tool_result_visibility", adapter.provider_id)
        confounded = True
    realized_visibility = contract.tool_result_visibility if visibility_ok else "full"

    realized = ExposureRealized(
        thinking_trace_to_agent=contract.thinking_trace_to_agent and "thinking_trace_to_agent" in satisfiable,
        reasoning_tokens_to_agent=contract.reasoning_tokens_to_agent and "reasoning_tokens_to_agent" in satisfiable,
        tool_result_visibility=realized_visibility,
        scratchpad_persistence=contract.scratchpad_persistence and "scratchpad_persistence" in satisfiable,
        exposure_confounded=confounded,
    )
    return ExposureResolved(contract=contract, realized=realized, confounded=confounded)
