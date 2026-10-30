"""Compare provider behavior on a fixed multi-turn tool-use exercise.

For each provider, select the most common tool/stop/turn fingerprint across
repetitions; ties use the first observed fingerprint. Compare selected tools,
normalized stop reasons, and turns to closure within the declared tolerance.
This tests a specified behavior on the probed model references, not identical
outputs on every repetition or general equivalence between providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from oaos2.models.gateway import call_model_gateway
from oaos2.models.raw_store import RawPayloadStore
from oaos2.models.types import (
    ModelRequest,
    NeutralBlock,
    NeutralMessage,
    SamplingParams,
    ToolSpec,
)
from oaos2.pricing.ledger import CostLedger
from oaos2.pricing.table import foundation_pricing_table
from oaos2.trace.spine import RunSpine
from oaos2.ulid import new_ulid


@dataclass
class TraceRun:
    tool_choices: list[str] = field(default_factory=list)
    stop_classes: list[str] = field(default_factory=list)
    turns_to_closure: int = 0


async def run_conformance_trace(adapter, run_dir: Path, *,
                                model_ref: str = "stub/deterministic",
                                max_output_tokens: int = 256,
                                platform_seed: int | None = None) -> TraceRun:
    """Drive a multi-turn tool-calling trace through ``adapter`` (M7 §10).

    ``max_output_tokens`` must clear a reasoning model's thinking burn (the
    2026-09-01 live probe saw gpt-5 exhaust 256 tokens before its first tool
    call); ``platform_seed`` rides to providers that honour a request seed."""
    spine = RunSpine(run_dir, run_id="conf")
    await spine.start()
    ledger = CostLedger(pricing_table=foundation_pricing_table())
    store = RawPayloadStore(run_dir)
    # The trace must EXERCISE a tool decision (a compliant model that can
    # answer without the tool produces a vacuous trace — live probe
    # 2026-09-01): the answer is only obtainable through the tool.
    tool = ToolSpec(name="search", description="look up a stored value by key",
                    parameters_schema={"type": "object",
                                       "properties": {"key": {"type": "string"}},
                                       "required": ["key"]})
    messages = [NeutralMessage("user", [NeutralBlock(
        kind="text",
        text="Report the stored access code. It is not known to you and not "
             "guessable: you MUST retrieve it with the search tool (key: "
             "'access_code'), then state it in one short sentence.")])]

    run = TraceRun()
    for _turn in range(4):  # bounded; closes at end_turn
        req = ModelRequest(
            call_id=new_ulid(), model_ref=model_ref, messages=list(messages),
            tools=[tool],
            sampling=SamplingParams(max_output_tokens=max_output_tokens,
                                    platform_seed=platform_seed),
        )
        resp = await call_model_gateway(req=req, adapter=adapter, ledger=ledger, spine=spine, raw_store=store)
        run.stop_classes.append(resp.stop_reason)
        run.turns_to_closure += 1
        tool_uses = [b for b in resp.content_blocks if b.kind == "tool_use"]
        if tool_uses:
            tu = tool_uses[0]
            run.tool_choices.append(tu.tool_name)
            messages.append(NeutralMessage("assistant", resp.content_blocks))
            messages.append(NeutralMessage("tool", [
                NeutralBlock(kind="tool_result", tool_call_id=tu.tool_call_id, text="42")
            ]))
        else:
            break
    await spine.finalize("completed")
    return run


def behavioral_equivalence(runs_a: list[TraceRun], runs_b: list[TraceRun], *, turn_tol: int = 0) -> bool:
    """PASS/FAIL predicate over N replications (M7 §2.2). Modal across reps."""
    a, b = _modal(runs_a), _modal(runs_b)
    if a.tool_choices != b.tool_choices:
        return False
    if a.stop_classes != b.stop_classes:
        return False
    if abs(a.turns_to_closure - b.turns_to_closure) > turn_tol:
        return False
    return True


def _modal(runs: list[TraceRun]) -> TraceRun:
    """The most common fingerprint across replications (M3 §2.2's replication
    band, landed with live stochastic parity 2026-09-01): stochastic providers
    at default sampling vary run-to-run, so the predicate compares MODAL
    behavior. Ties break to the earliest-seen fingerprint (deterministic)."""
    counts: dict[tuple, int] = {}
    order: dict[tuple, int] = {}
    for i, r in enumerate(runs):
        key = (tuple(r.tool_choices), tuple(r.stop_classes), r.turns_to_closure)
        counts[key] = counts.get(key, 0) + 1
        order.setdefault(key, i)
    best = max(counts, key=lambda k: (counts[k], -order[k]))
    return runs[order[best]]


# --------------------------------------------------------------------------- #
# Pre-dispatch cap: the estimate_tokens VALIDATED bound (M3 §3.2, §22).
#
# The cost cap is an admission check that must never under-project, or it could
# fail to prevent a mid-thought kill. The spec is explicit that this is a
# *validated* bound, not an asserted one: across a corpus of recorded requests,
# `estimate_tokens >= provider-reported actual input` must hold for EVERY entry,
# and the safety margin is widened until the corpus is clean. This is the gate
# that turns the per-request unit assertion into a corpus-level guarantee.
# --------------------------------------------------------------------------- #


@dataclass
class CorpusEntry:
    messages: list[NeutralMessage]
    tools: list[ToolSpec]
    reported_input_tokens: int  # the FULL input the provider billed (uncached-equivalent)
    call_id: str = ""


@dataclass
class EstimateValidationReport:
    n: int = 0
    undercounts: list[dict] = field(default_factory=list)  # entries where estimate < actual
    worst_ratio: float = float("inf")  # min(estimate/actual); <1.0 means an undercount exists
    suggested_margin_multiplier: float = 1.0  # factor to widen the margin until clean

    @property
    def clean(self) -> bool:
        """The cap is a validated bound iff NO entry under-counts (M3 §3.2)."""
        return not self.undercounts


def validate_estimate_corpus(adapter, corpus: list[CorpusEntry]) -> EstimateValidationReport:
    """Assert ``estimate_tokens >= reported_input`` across a corpus (M3 §3.2 gate).

    Any undercount fails the gate; ``suggested_margin_multiplier`` is the factor by
    which the adapter's margin must grow so the worst case clears (the spec's
    "widen the margin until the corpus is clean"). A clean report means the
    pre-dispatch cap is a *validated* upper bound on this corpus, not merely asserted.
    """
    report = EstimateValidationReport(n=len(corpus))
    worst = float("inf")
    for e in corpus:
        actual = e.reported_input_tokens
        estimate = adapter.estimate_tokens(e.messages, e.tools)
        if actual > 0:
            worst = min(worst, estimate / actual)
        if estimate < actual:
            report.undercounts.append({
                "call_id": e.call_id, "estimate": estimate, "actual": actual,
                "shortfall": actual - estimate,
            })
    report.worst_ratio = worst
    # If the worst ratio is below 1.0, the margin must grow by 1/worst (plus a hair)
    # to clear it; otherwise no widening is needed.
    report.suggested_margin_multiplier = (1.0 / worst) if (worst < 1.0 and worst > 0) else 1.0
    return report


def estimate_corpus_from_archive(run_dir: Path) -> list[CorpusEntry]:
    """Reconstruct a validation corpus from a real run archive (M3 §3.2, §17.1).

    Each ``model.invoked`` event references the verbatim request in ``raw/``; the
    matching ``model.responded`` carries the provider-reported ``usage``. We pair
    them by ``model_call_id`` and take the FULL input (``input_uncached_equiv`` when
    a cache split was reported, else ``input``) as the bound the estimate must clear.
    """
    from oaos2.trace.invariants import load_all_events

    store = RawPayloadStore(run_dir)
    events = load_all_events(run_dir)
    requests: dict[str, str] = {}  # model_call_id -> raw_provider_request_ref
    actuals: dict[str, int] = {}   # model_call_id -> reported full input tokens
    for e in events:
        cls, payload = e.get("event_class"), (e.get("payload") or {})
        call_id = e.get("model_call_id")
        if cls == "model.invoked" and payload.get("raw_provider_request_ref"):
            requests[call_id] = payload["raw_provider_request_ref"]
        elif cls == "model.responded":
            usage = payload.get("usage") or {}
            full = usage.get("input_uncached_equiv")
            if full is None:
                full = usage.get("input", 0)
            actuals[call_id] = full

    corpus: list[CorpusEntry] = []
    for call_id, ref in requests.items():
        if call_id not in actuals:
            continue  # a failed call (no usage) — nothing to bound
        req = store.get(ref).get("request", {})
        messages = [
            NeutralMessage(
                role=m.get("role", "user"),
                blocks=[
                    NeutralBlock(
                        kind=b.get("kind", "text"), text=b.get("text"),
                        tool_name=b.get("tool_name"), tool_call_id=b.get("tool_call_id"),
                        arguments=b.get("arguments"), provider_opaque=b.get("provider_opaque"),
                    )
                    for b in m.get("blocks", [])
                ],
            )
            for m in req.get("messages", [])
        ]
        tools = [
            ToolSpec(name=t.get("name", ""), description=t.get("description", ""),
                     parameters_schema=t.get("parameters_schema"))
            for t in req.get("tools", [])
        ]
        corpus.append(CorpusEntry(messages=messages, tools=tools,
                                  reported_input_tokens=actuals[call_id], call_id=call_id))
    return corpus
