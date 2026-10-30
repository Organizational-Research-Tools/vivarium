"""A scripted model and small helpers for offline runs (the public release).

Taken unchanged from ``tests/tasks/test_python_bug_repair_spike.py`` of the source repository,
whose bug-repair task is not part of this release; the workshop's tests and the quickstart use
them. The n-th scripted response is chosen by how many tool results the request carries, so a
script advances one tool per model call.
"""

from __future__ import annotations

from pathlib import Path

from oaos2.models.adapters.base import ModelBackendCapabilities, RawProviderResponse
from oaos2.models.types import ModelResponse, NeutralBlock, TokenSplit
from oaos2.trace.invariants import load_all_events

_FAKE_DIGEST = "sha256:fake"


def _tool(name: str, call_id: str, **arguments) -> dict:
    return {"kind": "tool_use", "tool_name": name, "tool_call_id": call_id,
            "arguments": arguments}


class _ScriptedStub:
    """Scripted model: the n-th response is chosen by how many tool results the
    request already carries, so the script advances exactly one tool per call."""

    provider_id = "repair_scripted_stub"

    def __init__(self, script: list[dict], runs_root: Path | None = None) -> None:
        self.script = script
        self.runs_root = runs_root
        self.seen_inbox: list[str] = []
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="none", context_window=200_000, supports_tools=True,
            provider_seed_support=True, prompt_cache_support=False,
            satisfiable_exposures=frozenset())

    def translate(self, req):
        return req

    async def invoke(self, payload) -> RawProviderResponse:
        req = payload
        n_results = sum(1 for m in req.messages for b in m.blocks
                        if getattr(b, "kind", "") == "tool_result")
        # Record every user-turn text so the test can assert what the agent saw.
        for m in req.messages:
            if m.role == "user":
                self.seen_inbox.append("\n".join(b.text or "" for b in m.blocks))
        step = self.script[min(n_results, len(self.script) - 1)]
        block = dict(step)
        hook = block.pop("before", None)
        if hook is not None and self.runs_root is not None:
            repo = next(self.runs_root.rglob("container_mount/agents/analyst/repo"))
            hook(repo)
        block["tool_call_id"] = f"c-{req.call_id[:8]}"
        return RawProviderResponse(payload={"model_ref": req.model_ref, "blocks": [block],
                                            "stop": "tool_use", "input_tokens": 5,
                                            "output_tokens": 5})

    def normalize(self, raw, req, raw_ref) -> ModelResponse:
        p = raw.payload
        blocks = [NeutralBlock(kind=b["kind"], text=b.get("text", ""),
                               tool_name=b.get("tool_name"), tool_call_id=b.get("tool_call_id"),
                               arguments=b.get("arguments")) for b in p["blocks"]]
        return ModelResponse(model_call_id=req.call_id, model_ref=req.model_ref,
                             stop_reason=p["stop"], content_blocks=blocks,
                             usage=TokenSplit(input=p["input_tokens"], output=p["output_tokens"]),
                             raw_provider_response_ref=raw_ref)

    def satisfiable_exposures(self):
        return set()

    def estimate_tokens(self, messages, tools):
        return 64


def _events(result):
    return load_all_events(result.run_dir)


def _kinds(events, cls: str):
    return [e for e in events if e["event_class"] == cls]
