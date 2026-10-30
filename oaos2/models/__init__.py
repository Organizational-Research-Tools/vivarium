"""Common model request types and the host-side call gateway.

The gateway checks capabilities and budgets, invokes an adapter, retains the
response, and records usage. Adapters translate provider formats and obtain
credentials on the host. Agent sequencing and tool execution live outside them."""

from oaos2.models.exposure import (
    ExposureResolved,
    ExposureUnsatisfiable,
    ModelExposureContract,
    resolve_exposure,
)
from oaos2.models.raw_store import RawPayloadStore
from oaos2.models.types import (
    ModelRequest,
    ModelResponse,
    NeutralBlock,
    NeutralMessage,
    SamplingParams,
    ToolSpec,
)

# NB: ``call_model_gateway`` is intentionally NOT re-exported here. Importing it
# would pull ``pricing`` into ``models`` package init, and since
# ``pricing.attribution`` imports ``models.types`` that creates an import cycle.
# Import it from the submodule: ``from oaos2.models.gateway import call_model_gateway``.

__all__ = [
    "ExposureResolved",
    "ExposureUnsatisfiable",
    "ModelExposureContract",
    "ModelRequest",
    "ModelResponse",
    "NeutralBlock",
    "NeutralMessage",
    "RawPayloadStore",
    "SamplingParams",
    "ToolSpec",
    "resolve_exposure",
]
