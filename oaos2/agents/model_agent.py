"""Build a model-driven agent behavior for the host-managed execution loop.

make_model_agent_behavior calls the model gateway, dispatches requested tools,
returns tool results, and continues until work ends or a limit stops it.
Tasks supply prompts and permitted tools. Context summarization and call limits
are part of this loop; provider adapters do not run an independent agent loop.
See agents/capacity.py, agents/tools.py, and models/gateway.py."""

from __future__ import annotations

import asyncio
import re
import time

import math
from dataclasses import replace

from oaos2.agents.tools import ToolContext, ToolResult, dispatch_tool
from oaos2.kernel.runtime import ActionPlan, ConversationVolleyIntent
from oaos2.models.adapters.base import estimate_input_tokens_chars
from oaos2.models.exposure import ModelExposureContract
from oaos2.agents.capacity import CapacityPolicy
from oaos2.models.gateway import call_model_gateway
from oaos2.pricing.ledger import CostCapWouldBreach
from oaos2.models.types import (
    BlockKind,
    CachePolicy,
    ModelRequest,
    NeutralBlock,
    NeutralMessage,
    ReasoningRequest,
    SamplingParams,
)
from oaos2.ulid import new_ulid

# Organic-arm deliberation (Stage 2-H): the fixed instruction appended to a deliberating
# agent's own system prompt when it holds the conversation floor. A constant of the apparatus
# (identical across arms) so the deliberation mechanism is not a per-arm variable.
_DELIBERATION_DONE_MARKER = "<satisfied/>"
# The DEFAULT in-conversation instruction (task-neutral). A pack normally overrides it via the
# manifest `deliberation_instruction` (→ TaskPack → the behavior's `deliberation_instruction`
# param), since what counts as substantive deliberation is task-specific; the default keeps a
# packless caller functional and pins the closure protocol (the JSON priority + done marker).
_DELIBERATION_INSTRUCTION = (
    "You are one member of a group jointly deciding the organization's objective. The other "
    "members speak for different concerns. This is a working discussion: do not paste data "
    "tables or write code here — argue substance and work toward a SHARED decision on the "
    "OBJECTIVE, which concerns to prioritize and how to trade them off, reasoning from the "
    "task materials. Take one turn at a time; be concise and engage with what others have "
    "actually said; do not just restate your own brief. When you genuinely agree with the "
    "group's current proposed objective, restate the agreed priority over the concerns as a "
    'JSON object like {"priority": ["...", "..."], "rationale": "..."} and end your message '
    f"with {_DELIBERATION_DONE_MARKER}. Do not signal agreement until you actually agree."
)


# Deliberation cache policy (M3 §3.1): the constant per-rep prefix (role packet +
# instruction + dossier) sits in the cached system slot; the transcript is rendered as
# one user message PER TURN (byte-identical across volleys, since turns only append)
# with a rolling `transcript_tail` breakpoint on the newest turn — so a rep's next
# volley cache-reads the whole prior transcript instead of re-billing it uncached
# (the O(volleys²) input cost of a deliberation). The closing "# Your turn" prompt
# stays AFTER the breakpoint: it is constant, so caching through it would break the
# byte-prefix match on the next, longer transcript. Lookback caveat: the provider
# matches a prior cache entry at most ~20 blocks back, so this pays off for groups
# of up to ~19 reps (one new turn message per intervening speaker). An apparatus
# constant, identical across arms/tiers — a cost mechanism, never a treatment.
# The system slot (packet + instruction + dossier) also carries a 1h lifetime: it is
# byte-identical for the same rep across every volley of a cell AND across cells of the
# same arm x tier, but consecutive same-arm cells in a shuffled sweep sit >5m apart.
# The transcript tail stays 5m — volleys within a deliberation are seconds apart.
DELIBERATION_CACHE_POLICY = CachePolicy(breakpoints=["system", "transcript_tail"],
                                        ttl_overrides={"system": "1h"})


REFUSAL_RETRIES = 4  # re-sends of a refused call within one turn before the turn ends unrecovered
# After a refused call has been re-sent twice, the agent's context is trimmed for the rest of the
# run (the PI's option B, October 11, 2026); after a third refusal one recap is forced. The
# G4 trigger probe found refusals switched on by one turn's combination of the agent's
# reasoning, generated code and a long printed output, and cured by removing any of them or the
# older history (library/experiments/evidence/g4_refusal_*_20261011*.json).
TRIM_KEEP_RECENT, TRIM_LIMIT_CHARS, TRIM_HEAD_CHARS = 4, 1200, 300


INBOX_HEAD = "# Upstream handoff (cont.)"


def _trim_context(msgs: list, heading: str = INBOX_HEAD) -> int:
    """Drop every reasoning block, and shorten tool outputs longer than TRIM_LIMIT_CHARS outside
    the last TRIM_KEEP_RECENT messages to their head and a note. In place; returns blocks changed.
    Records stay retrievable through the task's own tools.

    Messages received from other agents outside the last TRIM_KEEP_RECENT messages are shortened
    to a note as well (G5, October 15, 2026): a replay probe of G4's refused requests traced Claude
    Haiku 5.5's refusals to the accumulated messages from other agents (board posts), and this
    trim cut re-refusals of refused requests from about 65% to about 35%. The task's read tools
    reread them. ``heading`` is the pack's heading over mid-conversation deliveries (PC1's
    ``inbox_heading``; INBOX_HEAD by default)."""
    changed = 0
    keep_from = max(0, len(msgs) - TRIM_KEEP_RECENT)
    for i, m in enumerate(msgs):
        kept = [b for b in m.blocks if b.kind != BlockKind.THINKING.value]
        changed += len(m.blocks) - len(kept)
        m.blocks[:] = kept
        if i < keep_from:
            for b in m.blocks:
                if b.kind == BlockKind.TOOL_RESULT.value and len(b.text or "") > TRIM_LIMIT_CHARS:
                    omitted = len(b.text) - TRIM_HEAD_CHARS
                    b.text = b.text[:TRIM_HEAD_CHARS] + f"\n[... {omitted} characters of earlier output omitted ...]"
                elif (b.kind == BlockKind.TEXT.value and m.role == "user" and (b.text or "").startswith(heading)
                      and len(b.text) > len(heading) + 200):
                    # only messages from other agents go (board posts and notes); the platform's own
                    # notices (results, report results, the workshop's and a client's notices) stay
                    # (October 15, 2026)
                    items = re.split(r"\n(?=\[|# )", b.text[len(heading):].lstrip("\n"))
                    keep = [x for x in items if not x.startswith(("[board", "[note from"))]
                    omitted = sum(len(x) for x in items if x.startswith(("[board", "[note from")))
                    if omitted:
                        b.text = (f"{heading}\n" + "\n".join(keep)
                                  + f"\n[... {omitted} characters of earlier messages from others omitted; the read "
                                  "tools reread them ...]")
                        changed += 1
    msgs[:] = [m for m in msgs if m.blocks]
    return changed


def reported_per_estimated(resp, req) -> float | None:
    """The provider's reported input tokens for ``req`` over the local estimate of it, or None without a usable count
    (a refusal, a stub). Bounded, so that one odd reading cannot set an absurd threshold."""
    u = getattr(resp, "usage", None)
    if u is None or getattr(resp, "stop_reason", None) == "refusal":
        return None
    reported = u.input_uncached_equiv if u.input_uncached_equiv is not None else (u.input or 0) + (u.cache_read or 0)
    estimated = estimate_input_tokens_chars(req.messages, list(req.tools))
    if not reported or not estimated:
        return None
    return min(2.0, max(0.05, reported / estimated))


def effective_context_budget(budget: int, ratio: float | None) -> int:
    """The context budget in estimator units: unchanged on the estimator basis (``ratio`` None), else the reported-token
    budget divided by the agent's reported-to-estimated ratio."""
    return budget if not ratio else int(budget / ratio)



def cost_pressure_text(tool_context, spent_usd: float, cap_usd: float | None) -> str:
    """The wrap-up notice at cost pressure. For the built-in submission it names
    ``submit_results`` and asks for best current values. For a pack whose submission is a
    registered action (M8 §2) it names that action and states the facts, without telling
    the agent to stop analysis or to submit partial work: the September 17 rivalry pilot
    showed the generic text naming a tool the labs did not have and commanding partial
    submission against a protocol that requires complete evidence."""
    actions = getattr(tool_context, "task_actions", None) or {}
    submit_actions = sorted(n for n, a in actions.items() if getattr(a, "effect_class", "") == "submit")
    used = f"${spent_usd:.2f} of ${cap_usd:.2f}" if cap_usd else f"${spent_usd:.2f}"
    if submit_actions and getattr(tool_context, "cost_notice", None) == "plain":
        # PC1 x7 (October 18, 2026): in the capped MiniMax M3 x6 run the first restricted filing followed "If you
        # intend to submit, do it now"; a notice that tells a laboratory to file is participant text that leads.
        return (f"Notice: your organization's model budget is nearly exhausted ({used} used). When the cap is "
                "reached your participation ends.")
    if submit_actions:
        names = ", ".join(f"`{n}`" for n in submit_actions)
        return (f"Notice: your organization's model budget is nearly exhausted ({used} used). When the "
                f"cap is reached your participation ends and nothing is submitted for you. If you intend "
                f"to submit, do it now with {names} under the task's own rules; otherwise use what remains "
                "as you see fit.")
    allowed = getattr(tool_context, "allowed_tools", None)
    if actions and allowed is not None and "submit_results" not in allowed:
        # A role with registered actions and no way to submit at all (G4's executors):
        # naming `submit_results`, which it does not have, would be wrong (build audit,
        # October 9, 2026). State the facts only. A role that keeps the built-in
        # `submit_results` beside message actions (budget execution) gets the notice below.
        return (f"Notice: your organization's model budget is nearly exhausted ({used} used). When the "
                "cap is reached your participation ends.")
    # The built-in submission's notice states the same facts in task-neutral words. Until
    # 2026-09-25 it told every role to "STOP running analysis" and to submit partial
    # results, wording written for the analysis tasks (realism review, defect 4).
    return (f"Notice: your organization's model budget is nearly exhausted ({used} used). When the "
            "cap is reached your participation ends and nothing further is submitted for you. If "
            "you hold a duty you can complete, submit it now with `submit_results` with your best "
            "current content; otherwise use what remains as you see fit.")


async def _deliberation_volley(vreq, *, system_prompt, initial_user_text, model_ref, adapter,
                               ledger, raw_store, spine, agent_id, activity_class,
                               exposure_contract, confirmatory, temperature, caused_by,
                               instruction: str | None = None, on_admitted=None):
    """Produce one deliberation turn (a conversation volley) via a single model call, seeded with
    the agent's own brief + the discussion transcript. `done` is set when the agent assents (its
    text carries the done marker). On cost-cap, it assents so the group can close rather than hang.
    Pure of the agent loop — testable with a fake gateway. ``instruction`` overrides the default
    apparatus constant (pack-declared, TaskPack.deliberation_instruction — what counts as
    substantive deliberation is task-specific; held constant across tiers within a pack)."""
    conv_id = vreq["payload"]["conversation_id"]
    transcript = vreq["payload"].get("transcript", [])
    # The per-rep CONSTANT prefix lives in the cached system slot; the transcript is one
    # user message per turn under a rolling breakpoint (see DELIBERATION_CACHE_POLICY).
    # Consecutive user messages are combined into a single turn by the provider, so the
    # model sees the same discussion-so-far / your-turn framing as a single-block render.
    turn_msgs = [NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value,
                                                      text=f'{t["speaker"]}: {t["text"]}')])
                 for t in transcript] \
        or [NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value,
                                                 text="(you are opening the discussion)")])]
    dmsgs = [
        NeutralMessage("system", [NeutralBlock(kind=BlockKind.TEXT.value,
            text=f"{system_prompt}\n\n{instruction or _DELIBERATION_INSTRUCTION}\n\n{initial_user_text}")]),
        NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value,
                                             text="# The discussion so far")]),
        *turn_msgs,
        NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value,
                                             text="# Your turn\nRespond as the next speaker.")]),
    ]
    dreq = ModelRequest(
        call_id=new_ulid(), model_ref=model_ref, messages=dmsgs, tools=[],
        sampling=SamplingParams(max_output_tokens=1024, temperature=temperature),
        reasoning=ReasoningRequest(kind="none"), cache=DELIBERATION_CACHE_POLICY)
    try:
        resp = await call_model_gateway(
            req=dreq, adapter=adapter, ledger=ledger, spine=spine, raw_store=raw_store,
            activity_class=activity_class, exposure_contract=exposure_contract,
            confirmatory=confirmatory, agent_id=agent_id, caused_by=caused_by,
            on_admitted=on_admitted)
    except CostCapWouldBreach:
        return ConversationVolleyIntent(conversation_id=conv_id,
                                        text=f"(budget reached) {_DELIBERATION_DONE_MARKER}",
                                        done=True, budget_forced=True)
    text = "".join(b.text for b in resp.content_blocks if b.kind == BlockKind.TEXT.value).strip()
    return ConversationVolleyIntent(conversation_id=conv_id, text=text,
                                    done=(_DELIBERATION_DONE_MARKER in text),
                                    last_event_id=getattr(resp, "response_event_id", None))

# Per-agent context budget (M5 §2.6 / DESIGN §17.1): when the running context exceeds an
# agent's token budget, deterministically evict the OLDEST tool-result TEXT — stub-replacing
# it (keeping the block + tool_call_id so tool_use/tool_result pairing stays API-valid) rather
# than summarizing (a model call would be a stochastic confound). Protects the system prompt,
# the initial handoff, and the most recent turns. This makes bounded information-processing
# capacity (Galbraith/March-Simon) a tunable knob; it is a generic agent parameter, not
# task-specific. Compaction is a CONSTRAINT, not assistance — it is recorded as a
# `context.compaction` event, never an `intervention.recorded` (so it can't mislabel the
# outcome ASSISTED). Mutates the message list in place: once compacted, the context is gone.
_EVICT_KEEP_RECENT_MSGS = 4  # keep ~the last two turns (assistant + tool pairs) intact
_EVICTED_PREFIX = "[evicted:"


INBOX_SHORTEN_CHARS, INBOX_SHORTEN_HEAD = 2000, 600


def _shorten_inbox(msgs: list, keep_recent: int) -> int:
    """Shorten long incoming messages (user-role text) outside the last ``keep_recent`` messages to
    their head and a note; idempotent, so a shortened message stays stable for the provider cache.
    The fallback when summarizing and evicting tool output cannot reach the context budget."""
    changed = 0
    for m in msgs[2:max(2, len(msgs) - keep_recent)]:
        if m.role != "user":
            continue
        for b in m.blocks:
            text = b.text or ""
            if b.kind == BlockKind.TEXT.value and len(text) > INBOX_SHORTEN_CHARS and "characters of this message omitted" not in text:
                b.text = (text[:INBOX_SHORTEN_HEAD] + f"\n[... {len(text) - INBOX_SHORTEN_HEAD} characters of this "
                          "message omitted to respect the context budget; the read tools and records reread them ...]")
                changed += 1
    return changed


def _evict_to_budget(msgs: list[NeutralMessage], budget: int | None, toolspecs: list,
                     keep_recent: int = _EVICT_KEEP_RECENT_MSGS) -> list[dict]:
    """Evict oldest tool-result text until ``estimate_input_tokens_chars`` is within ``budget``.
    Deterministic; mutates ``msgs`` in place. Returns the evicted blocks' {tokens, tool_call_id}
    (empty if nothing was evicted)."""
    if budget is None or estimate_input_tokens_chars(msgs, toolspecs) <= budget:
        return []
    protected_tail = set(range(max(0, len(msgs) - keep_recent), len(msgs)))
    dropped: list[dict] = []
    for i, m in enumerate(msgs):
        if i <= 1 or i in protected_tail or m.role != "tool":
            continue  # protect system (0), initial handoff (1), recent turns; only tool results
        for b in m.blocks:
            if b.kind == BlockKind.TOOL_RESULT.value and b.text and not b.text.startswith(_EVICTED_PREFIX):
                tok = math.ceil(len(b.text) / 3 * 1.3)
                b.text = f"{_EVICTED_PREFIX} ~{tok} tokens of earlier tool output dropped to respect the context budget]"
                dropped.append({"tokens": tok, "tool_call_id": b.tool_call_id})
                if estimate_input_tokens_chars(msgs, toolspecs) <= budget:
                    return dropped
    return dropped


# Summarization compaction (the NATIVE "compact-and-continue" mechanism real agent harnesses
# use): when over budget, the PLATFORM summarizes the older span of the conversation with a
# fixed model + prompt and replaces it with a single recap, then continues. Held identical
# across all arms, so the summarizer is a CONSTANT of the apparatus (like the scheduler), not a
# per-arm variable — the realistic mechanism without the summarizer becoming a confound. Cost is
# attributed to the `compaction` OVERHEAD class; still recorded as `context.compaction` (a
# constraint), never an intervention.
_SUMMARIZE_SYSTEM = (
    "You compact an AI agent's working memory. Given the earlier part of its own work session, "
    "write a concise recap that preserves everything needed to CONTINUE the task: established "
    "facts and intermediate results (with their values), decisions made and why, what has been "
    "tried, and the current state. Do not invent or infer beyond the transcript. Write prose only: never a "
    "tool call, and never an action described as taken unless its result is in the transcript. Output only the recap."
)
_SUMMARY_PREFIX = "[Context summary — earlier work in this session, condensed]"
_SUMMARY_MAX_TOKENS = 2048  # the default recap ceiling; a pack may declare its own
# Appended to a recap cut to the pack's character limit (compaction_max_chars, October 12, 2026).
_SUMMARY_CUT_NOTE = ("\n[This recap exceeded its length limit and was cut; what followed is not kept. "
                     "Your records stay available through the task's tools.]")


def _cut_recap(summary: str, max_chars: int | None) -> tuple[str, int]:
    """The recap within ``max_chars``, cut at the last paragraph (or line) boundary before the limit, and the number
    of characters removed. A model that keeps to the requested length is never cut."""
    if not max_chars or len(summary) <= max_chars:
        return summary, 0
    head = summary[:max_chars]
    for sep in ("\n\n", "\n"):
        i = head.rfind(sep)
        if i > max_chars // 2:
            head = head[:i]
            break
    return head.rstrip(), len(summary) - len(head.rstrip())
# Appended to a recap the provider cut off at the ceiling, so the agent knows its memory
# is incomplete instead of reading a table that stops mid-row as the whole record. The
# September 18, 2026 materials control installed nine truncated recaps silently.
_SUMMARY_TRUNCATED_NOTE = ("\n[This recap was cut off at its length limit and is incomplete; "
                           "recover anything missing from your records and files.]")
# A recap that is not a recap: the summarizer continued the agent's work in the first person
# and wrote a tool call. The September 22, 2026 director control installed one as the
# agent's memory ("I'll register a prototype ... <tool_call>"), and the agent then treated
# the registration as done. Such output is refused once and the call retried with a
# reminder; a second failure is installed (the context must shrink) but marked.
_SUMMARY_FABRICATION_RE = re.compile(
    r"<tool_call>|</tool_call>|\[tool_call |\"arguments\"\s*:|\"name\"\s*:\s*\"[a-z_]+\"\s*,\s*\"(?:arguments|input)\"|"
    r"\A\s*(?:I'll |I will |Let me |I am going to |I'm going to )", re.I)
_SUMMARY_RETRY_NOTE = ("\n\nYour previous output was not a recap: it continued the agent's work in the first person "
                       "or contained a tool call. Write the recap now, in prose and in the required sections. "
                       "Never write a tool call. Never say an action was taken unless its result appears in the "
                       "session; an action the agent had decided on but not made is a pending action.")
_SUMMARY_REJECTED_NOTE = ("\n[This recap failed a format check and may describe actions that were never taken; "
                          "trust only your records and files for what has been done.]")


def _looks_fabricated(summary: str) -> bool:
    return bool(_SUMMARY_FABRICATION_RE.search(summary))


def _has_tool_use(m: NeutralMessage) -> bool:
    return any(b.kind == BlockKind.TOOL_USE.value for b in m.blocks)


def _recoverable_slots(tool_context) -> list[str]:
    """The slots whose case file this role must hold now: its bound duty plus any the
    procedure names (``protocol_state["recoverable_slots"]``: an office answering a query on
    an earlier case, a center with open queries; audit 2026-09-25 P1)."""
    slots: list[str] = []
    bound = getattr(tool_context, "submit_commitment_id", None)
    if bound:
        slots.append(bound)
    extra = getattr(tool_context, "protocol_state", {}).get("recoverable_slots")
    if callable(extra):
        try:
            for slot in extra() or []:
                if slot and slot not in slots:
                    slots.append(slot)
        except Exception:  # noqa: BLE001
            pass
    return slots


def _compactable_cut(msgs: list[NeutralMessage], keep_recent: int) -> int | None:
    """The boundary `cut` such that msgs[2:cut] is summarized and msgs[cut:] is kept — chosen so
    it never splits a tool_use/tool_result pair (the kept tail must not start with a dangling
    tool_result, and we must not summarize a tool_use whose result is kept). None if nothing is
    safely compactable."""
    cut = len(msgs) - keep_recent
    while cut > 2 and (msgs[cut].role == "tool" or _has_tool_use(msgs[cut - 1])):
        cut -= 1
    return cut if cut > 2 else None


def _render_span(msgs: list[NeutralMessage], lo: int, hi: int) -> str:
    parts = []
    for m in msgs[lo:hi]:
        text = " ".join(b.text for b in m.blocks if b.text)
        for b in m.blocks:
            if b.kind == BlockKind.TOOL_USE.value:
                text += f" [tool_call {b.tool_name}({b.arguments})]"
        if text.strip():
            parts.append(f"{m.role}: {text}")
    return "\n\n".join(parts)


def _apply_summary(msgs: list[NeutralMessage], cut: int, summary: str) -> dict:
    """Replace msgs[2:cut] with one recap user message (mutates in place; pairing-safe by
    construction of `cut`)."""
    n = cut - 2
    del msgs[2:cut]
    msgs.insert(2, NeutralMessage("user", [NeutralBlock(
        kind=BlockKind.TEXT.value, text=f"{_SUMMARY_PREFIX}\n{summary}")]))
    return {"policy": "summarize", "messages_summarized": n, "summary_chars": len(summary)}


async def _summarize_to_budget(msgs, budget, toolspecs, *, adapter, model_ref, ledger, raw_store,
                               spine, agent_id, caused_by, confirmatory,
                               on_admitted=None, instruction: str | None = None,
                               max_tokens: int | None = None, max_chars: int | None = None) -> dict | None:
    """Compact-and-continue: summarize the older span (one fixed model call) and splice in a
    recap. Returns stats, or None if nothing is safely compactable (caller falls back to evict).
    Propagates CostCapWouldBreach so the caller can fall back rather than die.

    ``on_admitted`` threads to the gateway's admission point (audit round 8
    P1-1): capacity charges only after ledger reservation succeeds and a real
    dispatch is imminent — never on response content, never on a rejected
    dispatch.

    ``instruction`` overrides the default summarizer prompt (pack-declared,
    TaskPack.compaction_instruction): what a recap must preserve is task-specific. It is
    held constant across a pack's arms, like the default. ``max_tokens`` is the recap's
    output ceiling (pack-declared, TaskPack.compaction_max_tokens). A recap the provider
    cut off at the ceiling is still installed, since the context must shrink, but it is
    marked for the agent and recorded as ``summary_truncated`` in the compaction event."""
    if estimate_input_tokens_chars(msgs, toolspecs) <= budget:
        return None
    cut = _compactable_cut(msgs, _EVICT_KEEP_RECENT_MSGS)
    if cut is None:
        return None
    span_text = _render_span(msgs, 2, cut)
    summary_req = ModelRequest(
        call_id=new_ulid(), model_ref=model_ref,
        messages=[NeutralMessage("system", [NeutralBlock(kind=BlockKind.TEXT.value, text=instruction or _SUMMARIZE_SYSTEM)]),
                  NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text=span_text)])],
        tools=[], sampling=SamplingParams(max_output_tokens=max_tokens or _SUMMARY_MAX_TOKENS, temperature=0.0),
        reasoning=ReasoningRequest(kind="none"), cache=CachePolicy(breakpoints=[]),
    )
    resp = await call_model_gateway(  # cost → `compaction` OVERHEAD class; may raise CostCapWouldBreach
        req=summary_req, adapter=adapter, ledger=ledger, spine=spine, raw_store=raw_store,
        activity_class="compaction", confirmatory=confirmatory, agent_id=agent_id, caused_by=caused_by,
        on_admitted=on_admitted,
    )
    summary = "".join(b.text for b in resp.content_blocks if b.kind == BlockKind.TEXT.value).strip()
    if not summary:
        return None  # empty summary → let the caller fall back to eviction
    retried = rejected = False
    if _looks_fabricated(summary):
        retried = True
        retry_req = ModelRequest(
            call_id=new_ulid(), model_ref=model_ref,
            messages=[NeutralMessage("system", [NeutralBlock(kind=BlockKind.TEXT.value,
                                                             text=(instruction or _SUMMARIZE_SYSTEM) + _SUMMARY_RETRY_NOTE)]),
                      NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text=span_text)])],
            tools=[], sampling=summary_req.sampling, reasoning=ReasoningRequest(kind="none"), cache=CachePolicy(breakpoints=[]),
        )
        resp2 = await call_model_gateway(
            req=retry_req, adapter=adapter, ledger=ledger, spine=spine, raw_store=raw_store,
            activity_class="compaction", confirmatory=confirmatory, agent_id=agent_id, caused_by=caused_by,
            on_admitted=on_admitted,
        )
        summary2 = "".join(b.text for b in resp2.content_blocks if b.kind == BlockKind.TEXT.value).strip()
        if summary2 and not _looks_fabricated(summary2):
            summary, resp = summary2, resp2
        else:
            rejected = True  # installed anyway (the context must shrink), marked for the agent
            summary = (summary2 or summary) + _SUMMARY_REJECTED_NOTE
    truncated = getattr(resp, "stop_reason", None) == "max_tokens"
    summary, cut_chars = _cut_recap(summary, max_chars)
    stats = _apply_summary(msgs, cut, summary + (_SUMMARY_CUT_NOTE if cut_chars else "")
                           + (_SUMMARY_TRUNCATED_NOTE if truncated and not cut_chars else ""))
    stats["summary_truncated"] = truncated
    if max_chars:
        stats["summary_cut_chars"] = cut_chars
    # A recap that still leaves the context over budget (the kept recent turns are large) is followed by dropping old
    # tool outputs, so that the next call does not start another recap at once (October 12, 2026: GLM-5.3-Flash).
    evicted = _evict_to_budget(msgs, budget, toolspecs)
    if evicted:
        stats["evicted_after_summary"] = {"blocks": len(evicted), "tokens": sum(d["tokens"] for d in evicted)}
    stats["summary_retried"] = retried
    stats["summary_rejected"] = rejected
    if getattr(resp, "response_event_id", None):
        stats["response_event_id"] = resp.response_event_id
    return stats


# Cache the static prefix (system + tools + the materials-bearing initial user message)
# AND roll a breakpoint at the latest turn so a long tool-using loop reuses the whole
# growing context instead of re-billing it (M3 §3.1; the policy is pinned in the manifest).
# The static-prefix entries carry a 1h lifetime: same-arm same-tier cells render that
# prefix byte-identically (verified on the 2026-07-05 archives), but a shuffled sweep
# separates them by more than the 5m default — 1h turns those cross-cell writes into
# 0.1x reads. The rolling tail stays 5m (per-cell content, reused within minutes).
# Uniform across arms — a cost mechanism, never a treatment.
_CACHE = CachePolicy(breakpoints=["system", "tools", "initial_user", "conversation_tail"],
                     ttl_overrides={"system": "1h", "tools": "1h", "initial_user": "1h"})
# Public handle so the runner can pin the cache-breakpoint policy into the manifest
# and confound_check can assert it is identical across compared cells (M3 §3.1).
DEFAULT_CACHE_POLICY = _CACHE


def make_model_agent_behavior(
    *,
    adapter,
    model_ref: str,
    system_prompt: str,
    initial_user_text: str,
    toolspecs: list,
    tool_context: ToolContext,
    ledger,
    raw_store,
    exposure_contract: ModelExposureContract | None = None,
    confirmatory: bool = True,
    activity_class: str = "work_modeling",
    reasoning_kind: str = "none",
    reasoning_budget: int | None = None,
    temperature: float = 1.0,
    max_output_tokens: int = 12288,  # must clear the thinking budget (8000 default) with
                                    # room for a full tool call — the D9 compose calls
                                    # think long over transcript-bearing contexts (smoke
                                    # 2026-07-07: 8192 truncated mid-thought -> retire)
    max_model_calls: int = 80,
    max_calls_per_slot: int | None = None,  # §11.6 per-slot capacity: model calls per bound
                                            # staged commitment; the counter resets when the
                                            # binding advances to another submission
    slot_ceiling_handler=None,  # async (slot_id) -> bool: runner-side closure that records
                                # capacity.slot_ceiling and platform-commits the
                                # contract-declared fallback for the starved slot
    budget_pressure_frac: float = 0.7,
    context_budget_tokens: int | None = None,
    compaction_policy: str = "summarize",  # "summarize" (native compact-and-continue; default)
                                           # | "evict" (deterministic drop). Eviction is also the
                                           # automatic fallback when summarization can't run.
    compaction_instruction: str | None = None,  # pack-declared summarizer prompt (None = default)
    inbox_heading: str | None = None,  # pack-declared heading over mid-conversation deliveries (None = default)
    compaction_max_tokens: int | None = None,  # pack-declared recap ceiling (None = 2048)
    compaction_max_chars: int | None = None,  # pack-declared recap length limit, enforced by cutting (None = none)
    # "estimate" (default): the context budget is in the local estimator's units. "reported" (PC1 x6, October 15,
    # 2026): in the provider's reported input tokens, the threshold scaled by this agent's own ratio of reported to
    # estimated input on its latest call (`effective_context_budget`); the x5 audit found the estimator counting
    # encrypted reasoning as text, so that equal nominal budgets gave gpt-5-mini a quarter of GLM's real context.
    context_budget_basis: str = "estimate",
    deliberation: bool = False,  # organic arm: when it holds a conversation floor, the agent
                                 # produces its turn (a volley) via a model call (Stage 2-H)
    deliberation_instruction: str | None = None,  # pack-declared volley instruction (None = default)
    readiness_gate=None,
    inbound_handler=None,
    post_submit_messages=None,
    retire_after_submit=None,  # () -> bool: was THIS submit the agent's final stage? None ⇒
                               # always (the legacy one-submission-per-agent behavior). A
                               # multi-stage role (draft -> revise, report -> comment; D9)
                               # yields instead, and resumes when the platform advances its
                               # submit binding to the next stage.
    continue_after_submit=None,  # () -> bool: after a non-final submit, is the newly bound
                                 # duty actionable NOW? True ⇒ stay in the same turn (clocked
                                 # megabatching — one working day, several duties); None or
                                 # False ⇒ the legacy yield. Wired by the runner from the
                                 # arrival-aware readiness gate, so an agent can never work
                                 # ahead of its own inbox.
    max_calls_per_turn=None,  # int: hard per-TURN model-call ceiling — in clocked runs a
                              # turn is one working day, so this is the fixed daily
                              # leadership-capacity constant (arm-identical apparatus,
                              # audit round 3 P1-2); megabatching lives inside it. None =
                              # unbounded (batched runs; the run-global cap still applies).
):
    """Build one agent's persistent model behavior and optional coordination hooks.

    readiness_gate() can make the agent yield without a model call while it waits
    for prerequisites. inbound_handler() records received items in agent state;
    post_submit_messages() supplies transfers after an accepted submission.
    Other callbacks control whether another submission slot is ready or the agent
    should retire. These hooks can also support a solo agent with several duties.

    confirmatory controls strict model-exposure checks at the gateway. Unsupported
    requested information is refused when True; other modes record the mismatch.
    Call and context limits are applied within this host-managed behavior."""

    async def behave(agent, rs, ctx) -> ActionPlan:
        """ONE reason→tool cycle = one engine action (M5 §2.2).

        The engine wraps each call in ``action.started``/``action.completed`` and
        re-invokes us while we return ``"continue"`` — so every model-call+tools
        iteration is its own captured action, the agent stays persistent (history
        + counters live in ``agent.state``), and the conversation is one session.
        """
        st = agent.state

        # Every call-count ceiling and its ordered interactions live in ONE
        # place (agents/capacity.py, repair item 6); this behavior only
        # consumes verdicts. Spend (usd/tokens) stays the ledger's, enforced
        # pre-dispatch inside call_model_gateway.
        policy = CapacityPolicy(st, max_model_calls=max_model_calls,
                                max_calls_per_turn=max_calls_per_turn,
                                max_calls_per_slot=max_calls_per_slot)
        async def _fire_pending_slot_fallback() -> None:
            # Audit round 4 P1-2: when the day (or run) budget ends the turn
            # first, a slot already at its ceiling must still get its declared
            # fallback — otherwise the org stalls a day (or forever, at
            # retirement) on a slot the contract says the platform closes.
            slot = getattr(tool_context, "submit_commitment_id", None)
            if slot_ceiling_handler is not None and policy.claim_slot_fallback(slot):
                await slot_ceiling_handler(slot)

        # Daily capacity (clocked runs): at the ceiling the working day ends —
        # unfinished duties resume the next day. Charges land after the
        # readiness gate below, so yields never spend the day's budget.
        policy.begin_turn(ctx.turn_id)
        opening_verdict = policy.exhausted()
        if opening_verdict is not None:
            await _fire_pending_slot_fallback()
            return ActionPlan(result="retire" if opening_verdict == "global" else "finish_turn")

        # Staged exogenous packets enter the model context as fresh user turns.
        # The runtime already tied these observations causally to environment.event;
        # this is only the provider-neutral presentation of the participant payload.
        environment_packets = [o for o in ctx.observations
                               if o.get("kind") == "environment_event"]
        environment_text = ""
        if environment_packets:
            import json as _json
            environment_text = "# New field observations\n" + "\n\n".join(
                _json.dumps(o.get("payload", {}), sort_keys=True, indent=2)
                for o in environment_packets
            )

        # Accumulate inbound handoffs/clarifications EVERY action (even while not yet
        # ready / before the loop starts) so a message that arrives while we are yielding
        # is not dropped when the mailbox is drained (M5 _observe drains per action).
        if inbound_handler is not None:
            inbound_handler(ctx.observations, st)

        # Organic-arm deliberation (Stage 2-H): if we hold a conversation floor (a volley is
        # requested), produce our turn via one model call and return it as a conversation volley.
        # This runs BEFORE the readiness gate — deliberation precedes the gated work phase, and
        # the agent resumes its normal tool loop only once the deliberation has committed.
        if deliberation:
            vreq = next((o for o in ctx.observations
                         if o.get("kind") == "conversation_volley_request"), None)
            # A volley is a provider call: it honors the run-global ceiling too
            # (audit round 5 P1-4). At the ceiling, fall through — the global
            # check below retires the agent with its fallback discipline.
            if vreq is not None and not policy.global_exhausted():
                intent = await _deliberation_volley(
                    vreq, system_prompt=system_prompt, initial_user_text=initial_user_text,
                    model_ref=model_ref, adapter=adapter, ledger=ledger, raw_store=raw_store,
                    spine=rs.spine, agent_id=agent.agent_id, activity_class=activity_class,
                    exposure_contract=exposure_contract, confirmatory=confirmatory,
                    temperature=temperature, caused_by=ctx.caused_by,
                    # contract-declared per-conversation override (e.g. ratification) wins
                    # over the pack's deliberation default; both are apparatus constants
                    instruction=(vreq["payload"].get("volley_instruction")
                                 or deliberation_instruction),
                    on_admitted=policy.charge_provider_call)
                return ActionPlan(conversation_volley=intent, last_event_id=intent.last_event_id)

        # Yield cheaply while prerequisites are unmet — before the loop starts (a downstream
        # role waiting on `blocks`) AND between stages (D9: a committed draft/report parks
        # the agent until the platform advances its submit binding). A started agent's stale
        # admission gate can grant one spurious turn (the scheduler pass that would withhold
        # it hasn't re-run since the stage completed): kick so the next pass re-evaluates,
        # and yield WITHOUT a model call — no spin, no spend, no refused-submit loop.
        if readiness_gate is not None and not readiness_gate():
            if st.get("_started"):
                rs.kick_scheduler()
            return ActionPlan(result="finish_turn")

        msgs: list[NeutralMessage] = st.get("messages")
        if msgs is None:
            st["_started"] = True
            user_text = initial_user_text
            folded = st.get("inbox_text")
            if folded:  # seed the first user turn with the upstream handoff payload
                user_text = f"{initial_user_text}\n\n{inbox_heading or '# Upstream handoff'}\n{folded}"
            if environment_text:
                user_text = f"{user_text}\n\n{environment_text}"
            snapshot0 = st.get("clock_snapshot")
            if snapshot0:  # current day line on the seeding turn too (P2-9)
                user_text = f"{user_text}\n\n{snapshot0}"
                st["clock_snapshot_sent"] = snapshot0
            msgs = [
                NeutralMessage("system", [NeutralBlock(kind=BlockKind.TEXT.value, text=system_prompt)]),
                NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text=user_text)]),
            ]
            st["messages"] = msgs
            st.setdefault("calls", 0)  # deliberation may already have spent calls
            st["inbox_consumed"] = len(folded or "")
        else:
            if environment_text:
                msgs.append(NeutralMessage("user", [NeutralBlock(
                    kind=BlockKind.TEXT.value, text=environment_text)]))
            # Fold any handoff text that arrived AFTER the conversation was seeded, as a
            # NEW user turn — so the upstream artifact reaches the agent regardless of
            # scheduler-kick timing (not only when the first message was built). Robust to
            # the handoff landing a beat after the readiness gate opened (review of §5).
            inbox = st.get("inbox_text", "")
            consumed = st.get("inbox_consumed", 0)
            if len(inbox) > consumed:
                msgs.append(NeutralMessage("user", [NeutralBlock(
                    kind=BlockKind.TEXT.value, text=f"{inbox_heading or INBOX_HEAD}\n{inbox[consumed:]}")]))
                st["inbox_consumed"] = len(inbox)
            # Latest clock snapshot only (audit round 3 P2-9): one fresh day
            # line per acted turn; stale day-notices never reach the model.
            snapshot = st.get("clock_snapshot")
            if snapshot and snapshot != st.get("clock_snapshot_sent"):
                msgs.append(NeutralMessage("user", [NeutralBlock(
                    kind=BlockKind.TEXT.value, text=snapshot)]))
                st["clock_snapshot_sent"] = snapshot

        if policy.global_exhausted():
            await _fire_pending_slot_fallback()  # audit round 4 P1-2
            return ActionPlan(result="retire")  # model-call ceiling (safety; cost is primary)

        last_event = ctx.caused_by

        # Per-slot model-call ceiling (§11.6 capacity binding; INSTRUMENT_DESIGN §1).
        # Slot-scoped: the counter resets when the staged binding advances.  At
        # ceiling-1 the agent gets one final-call warning — a declared apparatus
        # CONSTANT, uniform across every role and arm, so a constraint like
        # `context.compaction`, never an intervention.  At the ceiling the platform
        # closes the slot through the contract-declared fallback (runner handler) and
        # the agent yields until its binding advances.
        if max_calls_per_slot and slot_ceiling_handler is not None:
            slot = getattr(tool_context, "submit_commitment_id", None)
            policy.bind_slot(slot)
            if policy.slot_exhausted(slot):
                if policy.claim_slot_fallback(slot):
                    await slot_ceiling_handler(slot)
                return ActionPlan(result="finish_turn")
            if policy.claim_slot_warning(slot):
                last_event = await rs.spine.emit_event(
                    "context.pressure_warning", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                    caused_by=last_event,
                    payload={"kind": "slot_call_pressure", "commitment_id": slot,
                             "max_calls_per_slot": max_calls_per_slot})
                msgs.append(NeutralMessage("user", [NeutralBlock(
                    kind=BlockKind.TEXT.value,
                    text=(f"This is the final model call available for the current "
                          f"submission slot (`{slot}`). Call submit_results NOW with your "
                          "best current content for the required fields."))]))

        # Minimal soft pressure ladder (Tier-B placeholder): once EITHER the cost cap
        # OR the model-call ceiling is near, nudge the agent ONCE to submit now, so a
        # hard limit doesn't terminate it unscored. Recorded as an Intervention (§19).
        cap = getattr(ledger, "cap_usd", float("inf"))
        cost_frac = (ledger.pressure_fraction() if hasattr(ledger, "pressure_fraction")
                     else ledger.spent_usd / cap if cap != float("inf") else 0.0)
        call_frac = policy.call_fraction()
        if not st.get("_pressured") and max(cost_frac, call_frac) >= budget_pressure_frac:
            st["_pressured"] = True
            last_event = await rs.spine.emit_event(
                "context.pressure_warning", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                caused_by=last_event,
                payload={"kind": "cost_pressure", "spent_usd": ledger.spent_usd, "cap_usd": cap,
                         "spent_output_tokens": getattr(ledger, "spent_output_tokens", 0),
                         "cap_output_tokens": getattr(ledger, "cap_output_tokens", None)},
            )
            # Thread the intervention INTO the causal chain (last_event ← intervention),
            # so everything downstream — including the eventual state.committed — has it
            # as a causal ancestor and the outcome is correctly labelled ASSISTED
            # (M6 §3.3). Emitting it as a sibling would mislabel the run unassisted.
            last_event = await rs.spine.emit_event(
                "intervention.recorded", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                caused_by=last_event, payload={"kind": "cost_pressure_wrapup", "class": "recorded"},
            )
            msgs.append(NeutralMessage("user", [NeutralBlock(
                kind=BlockKind.TEXT.value,
                text=cost_pressure_text(tool_context, ledger.spent_usd, cap))]))

        # Bounded information-processing capacity: if the running context exceeds this agent's
        # budget, compact BEFORE the call. Default is the native "compact-and-continue" — the
        # platform summarizes the older span (one fixed model call) and continues; eviction is
        # the deterministic fallback when summarization can't run (cost cap / nothing to summarize).
        # Recorded as a constraint (`context.compaction`), NEVER an intervention — so enforcing
        # capacity can't mislabel the outcome ASSISTED.
        # once per refusal episode (October 18, 2026): trimming before every later call shortened the
        # message that had just left the recent window, changing the cached prefix on each call, so the
        # provider cache reused only the system prompt (a Haiku 5.5 run cost $9.65 instead of ~$2)
        if st.pop("_trim_pending", False):
            _trim_context(msgs, inbox_heading or INBOX_HEAD)
        if msgs and msgs[-1].role == "assistant":
            # A turn resumed with nothing new (a wait that ran out) would otherwise end the
            # conversation on the agent's own message: a prefill, which Claude Haiku 5.5 refuses
            # (400, October 11, 2026). A neutral note keeps the last message the user's.
            msgs.append(NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="(No new messages.)")]))
        forced = bool(st.pop("_force_compaction", False))
        if context_budget_tokens is not None:
            _toolspecs = list(toolspecs)
            before = estimate_input_tokens_chars(msgs, _toolspecs)
            # the budget on PC1's reported-token basis (October 15, 2026; a preset option), in estimator units
            _ratio = st.get("_ctx_ratio") if context_budget_basis == "reported" else None
            context_budget_tokens_eff = effective_context_budget(context_budget_tokens, _ratio)
            # after a compaction that could not reach the budget, wait until the context has grown by
            # a tenth of the budget before trying again (October 18, 2026: a lead whose context was
            # mostly protected inbox text was "compacted" 167 times, each call re-sent uncached)
            floor = st.get("_compaction_floor")
            futile = (not forced and floor is not None and before < floor + context_budget_tokens_eff // 10)
            if (before > context_budget_tokens_eff and not futile) or forced:
                stats = None
                if compaction_policy == "summarize":
                    try:
                        # Capacity charges at the GATEWAY admission point
                        # (post-reservation, pre-invoke; audit round 8 P1-1) —
                        # never on response content or a rejected dispatch.
                        stats = await _summarize_to_budget(
                            msgs, min(context_budget_tokens_eff, max(1, before // 2)) if forced
                            else context_budget_tokens_eff, _toolspecs, adapter=adapter,
                            model_ref=model_ref, ledger=ledger, raw_store=raw_store, spine=rs.spine,
                            agent_id=agent.agent_id, caused_by=last_event, confirmatory=confirmatory,
                            on_admitted=policy.charge_provider_call,
                            instruction=compaction_instruction,
                            max_tokens=compaction_max_tokens, max_chars=compaction_max_chars)
                    except CostCapWouldBreach:
                        stats = None  # can't afford to summarize → fall back to eviction below
                if stats is None:  # eviction (explicit policy, or summarize fallback)
                    dropped = _evict_to_budget(msgs, min(context_budget_tokens_eff, max(1, before // 2)) if forced
                                               else context_budget_tokens_eff, _toolspecs)
                    if dropped:
                        stats = {"policy": "evict",
                                 "tokens_dropped": sum(d["tokens"] for d in dropped),
                                 "blocks_evicted": len(dropped)}
                if estimate_input_tokens_chars(msgs, _toolspecs) > context_budget_tokens_eff:
                    # neither route reached the budget: shorten long incoming messages outside the
                    # recent ones, once each (their records stay in the task's files and read tools)
                    shortened = _shorten_inbox(msgs, _EVICT_KEEP_RECENT_MSGS)
                    if shortened:
                        stats = {**(stats or {"policy": "inbox_shortened"}), "inbox_messages_shortened": shortened}
                after_all = estimate_input_tokens_chars(msgs, _toolspecs)
                st["_compaction_floor"] = after_all if after_all > context_budget_tokens_eff else None
                if stats is not None:
                    # Recoverable records survive compaction inside a duty (2026-09-25):
                    # the case file a duty notice carried may sit in the summarized span,
                    # and a recap is not obliged to keep it. Re-deliver the current slot's
                    # case file after the recap, exactly as the runner does when a slot
                    # binds. Apparatus text, arm-identical; recorded on the event.
                    redelivered = False
                    restated = False  # the bound commitment has been restated after this recap
                    builder = getattr(rs, "case_file_builder", None)
                    if builder is not None:
                        for slot in _recoverable_slots(tool_context):
                            try:
                                case_file = builder(slot, agent.agent_id)
                            except Exception:  # noqa: BLE001 — never let re-delivery kill a turn
                                case_file = ""
                            if case_file:
                                bound = getattr(tool_context, "submit_commitment_id", None)
                                head = (f"# Current commitment\nYour currently authorized submission is "
                                        f"`{slot}`. Its case file is re-delivered below because your "
                                        "earlier context was compacted.\n"
                                        if slot == bound else
                                        f"# Case file for `{slot}` (a case you were queried on; not your "
                                        "current duty), re-delivered because your earlier context was "
                                        "compacted\n")
                                msgs.append(NeutralMessage("user", [NeutralBlock(
                                    kind=BlockKind.TEXT.value, text=head + case_file)]))
                                st[f"_case_file_seen:{slot}"] = case_file
                                redelivered = True
                                if slot == getattr(tool_context, "submit_commitment_id", None):
                                    restated = True
                    # A bound duty without a case file (an office's rule log, a plan) was
                    # not restated at all: after a recap that kept nothing the role could
                    # not know which submission it owed, and two refused submissions abort
                    # the run (LK1 integration, 2026-10-01). A commitment whose submission
                    # declares ``restate_after_compaction`` is restated with its duty note.
                    # Opt-in per contract profile, so no other study's apparatus text moves;
                    # arm-identical within a profile; recorded on the event.
                    bound = getattr(tool_context, "submit_commitment_id", None)
                    coordinator = getattr(tool_context, "coordinator", None)
                    if bound and not restated and coordinator is not None and bound not in coordinator.committed:
                        try:
                            sub = coordinator.contract.commitment(bound).submission or {}
                        except Exception:  # noqa: BLE001 — never let a restatement kill a turn
                            sub = None
                        if sub is not None and sub.get("restate_after_compaction"):
                            required = list(sub.get("required", []))
                            note = str(sub.get("duty_note") or "").strip()
                            text = (f"# Current commitment\nYour currently authorized submission is `{bound}`. "
                                    "It is restated because your earlier context was compacted."
                                    + (f" Required top-level JSON fields: {', '.join(required)}." if required else "")
                                    + (f" {note}" if note else ""))
                            msgs.append(NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text=text)]))
                            restated = True
                    last_event = await rs.spine.emit_event(
                        "context.compaction", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                        caused_by=stats.pop("response_event_id", None) or last_event,
                        payload={"budget_tokens": context_budget_tokens, "tokens_before": before,
                                 **({"budget_basis": "reported", "reported_per_estimated": _ratio,
                                     "budget_estimator_units": context_budget_tokens_eff}
                                    if context_budget_basis == "reported" else {}),
                                 "tokens_after": estimate_input_tokens_chars(msgs, _toolspecs),
                                 "case_file_redelivered": redelivered, "commitment_restated": restated,
                                 "reason": "refusal" if forced else "budget", **stats},
                    )

        # The case file at EVERY decision (2026-09-25): a binding that advanced inline
        # carried the file as rendered at that moment; a report committed since then is
        # re-delivered to the mailbox for the NEXT turn, while this turn may decide now.
        # Refresh a stale file before the call, once per change, unless it is already in
        # the recent context verbatim.
        _builder = getattr(rs, "case_file_builder", None)
        if _builder is not None:
            for _slot in _recoverable_slots(tool_context):
                try:
                    _current = _builder(_slot, agent.agent_id)
                except Exception:  # noqa: BLE001 — never let a refresh kill a turn
                    _current = ""
                _key = f"_case_file_seen:{_slot}"
                if _current:
                    # "present" means present in the context that survives: everything after
                    # the last recap. A file shown before a recap is gone and comes back here.
                    _start = 0
                    for _i, _m in enumerate(msgs):
                        if any((b.text or "").startswith(_SUMMARY_PREFIX) for b in _m.blocks
                               if getattr(b, "text", None)):
                            _start = _i
                    _present = any(_current in (b.text or "") for m in msgs[_start:] for b in m.blocks
                                   if getattr(b, "text", None))
                    if not _present:
                        _bound = getattr(tool_context, "submit_commitment_id", None)
                        _head = (f"# Case file update for `{_slot}`, your currently authorized submission\n"
                                 if _slot == _bound else
                                 f"# Case file update for `{_slot}` (a case you were queried on; not your "
                                 "current duty)\n")
                        msgs.append(NeutralMessage("user", [NeutralBlock(
                            kind=BlockKind.TEXT.value,
                            text=(_head + "A record or exchange on this case changed since it was last "
                                  "shown to you, or it is no longer in your context; the current file "
                                  "follows.\n" + _current))]))
                    st[_key] = _current

        req = ModelRequest(
            call_id=new_ulid(),
            model_ref=model_ref,
            messages=list(msgs),
            tools=list(toolspecs),
            sampling=SamplingParams(max_output_tokens=max_output_tokens, temperature=temperature),
            reasoning=ReasoningRequest(kind=reasoning_kind, budget_tokens=reasoning_budget),
            cache=_CACHE,
        )
        # Re-check BOTH ceilings AFTER compaction/deliberation charges (audit
        # rounds 5 P1-4 and 6 P1-1): a compaction call may have consumed the
        # day's — or the run's — last call. The working day ends (context
        # already compacted, duties resume tomorrow) or the agent retires;
        # either way the starved slot's fallback fires first.
        verdict = policy.exhausted()
        if verdict is not None:
            await _fire_pending_slot_fallback()
            return ActionPlan(result="finish_turn" if verdict == "day" else "retire",
                              last_event_id=last_event)
        # The PI's stop (RuntimeState.request_stop): no new model call is dispatched.
        if getattr(rs, "stop_requested", False):
            return ActionPlan(result="retire", last_event_id=last_event)

        # Pre-dispatch cap lives in the gateway; CostCapWouldBreach propagates → the
        # engine records a cost_capped turn (no mid-thought kill). Capacity
        # charges inside the gateway at admission (audit round 8 P1-1).
        request_binding = tool_context.submit_commitment_id
        _call_started = time.monotonic()
        resp = await call_model_gateway(
            req=req, adapter=adapter, ledger=ledger, spine=rs.spine, raw_store=raw_store,
            activity_class=activity_class, exposure_contract=exposure_contract,
            confirmatory=confirmatory, agent_id=agent.agent_id, caused_by=last_event,
            # Final-stage settlement reserve: only calls whose CURRENT binding is the
            # contract's final scored commitment may draw on the reserved tail of a
            # token-matched pool. Volleys and compaction stay non-exempt by default.
            reserve_exempt=(tool_context.submit_commitment_id
                            == getattr(tool_context, "final_commitment_id", None)),
            on_admitted=policy.charge_provider_call,
        )
        policy.charge_slot_call()
        # A procedure's floor on the duration of one step of work (G4, October 12, 2026): an
        # answered call is held until the floor has passed, so an agent acts at most once per
        # floor. With a floor per action instead, the step lasts the floor times its number of
        # actions (tool calls other than waiting; a step without one counts as one), so that
        # batching actions into one call does not buy time. Refused calls are not held (a
        # retry is not work). Recorded for the reader.
        _ps = getattr(tool_context, "protocol_state", None) or {}
        _floor = float(_ps.get("step_floor_s") or 0)
        _per_action = float(_ps.get("action_floor_s") or 0)
        if _per_action > 0 and resp.stop_reason != "refusal":
            _n = sum(1 for b in resp.content_blocks
                     if b.kind == BlockKind.TOOL_USE.value and b.tool_name != "wait")
            _floor = max(_floor, _per_action * max(1, _n))
        if _floor > 0 and resp.stop_reason != "refusal":
            _held = _floor - (time.monotonic() - _call_started)
            if _held > 0:
                await asyncio.sleep(_held)
                last_event = await rs.spine.emit_event(
                    "intervention.recorded", agent_id=agent.agent_id, turn_id=ctx.turn_id, caused_by=last_event,
                    payload={"kind": "step_held", "class": "mechanical", "held_s": round(_held, 3),
                             "floor_s": _floor})
        if context_budget_basis == "reported":
            _r = reported_per_estimated(resp, req)
            if _r is not None:
                st["_ctx_ratio"] = _r
        tally = getattr(rs, "provider_tally", None)
        if isinstance(tally, dict):
            tally["responses"] = tally.get("responses", 0) + 1
            tally["refusals"] = tally.get("refusals", 0) + (resp.stop_reason == "refusal")
        if resp.stop_reason == "refusal":
            # A provider safety classifier declined the call (Claude 5-generation models,
            # October 2026). The provider's guidance is to treat any partial output as
            # incomplete and discard it: no tool call in it is executed and the response is
            # not kept in the context (a kept thinking-only message made the next request
            # invalid). The call is retried with the same model, at most REFUSAL_RETRIES times
            # per turn (the PI, October 11, 2026: most refusals do not recur on a re-send); a
            # further refusal ends the turn and is counted as unrecovered. Mechanical, recorded, raw response retained. The
            # model is never switched within a run; a procedure may end a run whose refusals
            # exceed its bound (``RuntimeState.provider_tally``).
            refusals = st.get("_refusals_this_turn:" + str(ctx.turn_id), 0) + 1
            st["_refusals_this_turn:" + str(ctx.turn_id)] = refusals
            last_event = await rs.spine.emit_event(
                "intervention.recorded", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                caused_by=getattr(resp, "response_event_id", None) or last_event,
                payload={"kind": "refusal_discarded", "class": "mechanical", "attempt": refusals,
                         "max_retries": REFUSAL_RETRIES, "raw_provider_response_ref": resp.raw_provider_response_ref})
            if refusals <= REFUSAL_RETRIES:
                step = None
                if refusals == 2:
                    st["_trim_pending"], step = True, "context_trimmed_after_refusal"
                elif refusals == 3 and context_budget_tokens is not None:
                    st["_force_compaction"], step = True, "recap_forced_after_refusal"
                if step:
                    last_event = await rs.spine.emit_event(
                        "intervention.recorded", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                        caused_by=last_event, payload={"kind": step, "class": "mechanical"})
                return ActionPlan(result="continue", last_event_id=last_event)
            if isinstance(tally, dict):
                tally["unrecovered"] = tally.get("unrecovered", 0) + 1
                per = tally.setdefault("unrecovered_by_agent", {})
                per[agent.agent_id] = per.get(agent.agent_id, 0) + 1
            last_event = await rs.spine.emit_event(
                "intervention.recorded", agent_id=agent.agent_id, turn_id=ctx.turn_id, caused_by=last_event,
                payload={"kind": "refusal_unrecovered", "class": "mechanical", "attempts": refusals})
            # like a turn that ended without a tool call: the procedure may make it a bounded
            # wait, so the agent does not start the next turn at once and meet the same refusal
            may_end = getattr(tool_context, "protocol_state", {}).get("may_end_turn")
            if callable(may_end):
                may_end()
            return ActionPlan(result="finish_turn", last_event_id=last_event)
        kept = list(resp.content_blocks)
        while kept and kept[-1].kind == BlockKind.THINKING.value:
            # The provider refuses an assistant message whose final block is thinking (400,
            # October 10, 2026: a response that spent its output on reasoning alone). The
            # trailing reasoning is not kept in the context; the raw response retains it.
            kept.pop()
        if kept:
            msgs.append(NeutralMessage("assistant", kept))

        # Surface the agent's reasoning on the spine (Narration + ReasoningTelemetry),
        # linked to the verbatim raw payload — so the reasoning is first-class and
        # queryable, not only recoverable from raw/ (DESIGN §9, §17.1).
        narration = "".join(b.text for b in resp.content_blocks if b.kind == BlockKind.TEXT.value)
        thinking = "".join(b.text for b in resp.content_blocks if b.kind == BlockKind.THINKING.value)
        last_event = await rs.spine.emit_event(
            "reasoning.step", agent_id=agent.agent_id, turn_id=ctx.turn_id,
            caused_by=getattr(resp, "response_event_id", None) or last_event,
            model_call_id=resp.model_call_id,
            payload={
                "narration": narration[:8000],
                "thinking": thinking[:8000],  # populated only when thinking is exposed
                "raw_provider_response_ref": resp.raw_provider_response_ref,
                "stop_reason": resp.stop_reason,
                "usage": resp.usage.as_dict(),
            },
        )

        tool_uses = [b for b in resp.content_blocks if b.kind == BlockKind.TOOL_USE.value]
        if not tool_uses:
            # Backstop counters are keyed by the CURRENTLY OWED commitment: D9 staged
            # composition reuses one agent across draft→final (report→comment), and a
            # per-lifetime flag spent at the draft stage left the final stage bare.
            owed = tool_context.submit_commitment_id
            if (resp.stop_reason == "max_tokens"
                    and not st.get(f"_truncation_retried:{owed}")):
                # The output limit cut the response off mid-thought BEFORE any tool call
                # (not a decision to stop). Retiring here killed the smoke integrator
                # (2026-07-07): the composer thought long over a transcript-bearing
                # context and died at the cap. ONE bounded continuation nudge per owed
                # commitment — a MECHANICAL intervention (confound-excluded like marker
                # repair).
                st[f"_truncation_retried:{owed}"] = True
                last_event = await rs.spine.emit_event(
                    "intervention.recorded", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                    caused_by=last_event,
                    payload={"kind": "output_truncation_retry",
                             "class": "mechanical", "stop_reason": resp.stop_reason})
                msgs.append(NeutralMessage("user", [NeutralBlock(
                    kind=BlockKind.TEXT.value,
                    text="(Your response hit the output-token limit before any tool call. "
                         "Continue: keep further reasoning brief and make the tool call now.)")]))
                return ActionPlan(result="continue", last_event_id=last_event)
            # A procedure may declare that ending the turn without a submission is the
            # right move now (the budget exchange: waiting on a reply, or having
            # assented; 2026-09-25) — then this is a finished turn, not a reminder.
            may_end = getattr(tool_context, "protocol_state", {}).get("may_end_turn")
            if callable(may_end) and may_end():
                return ActionPlan(result="finish_turn", last_event_id=last_event)
            nudges = st.get(f"_prose_nudges:{owed}", 0)
            # A pack whose submissions are registered actions (M8 §2) owns its own
            # submission semantics; the submit_results reminder would be wrong.
            pack_owns_submission = any(
                a.effect_class == "submit"
                for a in (getattr(tool_context, "task_actions", None) or {}).values())
            # A role with pack actions but no way to submit (G4's executors) is not reminded to
            # call submit_results, a tool it lacks (October 12, 2026: reminders reached the
            # executors after the director retired).
            allowed = getattr(tool_context, "allowed_tools", None)
            if getattr(tool_context, "task_actions", None) and allowed is not None and "submit_results" not in allowed:
                pack_owns_submission = True
            if (owed not in tool_context.coordinator.committed and nudges < 2
                    and not pack_owns_submission):
                # The agent still OWES its submission but answered in prose and stopped —
                # post-D9 a single composer is a single point of failure (the smoke-batch
                # rep02 integrator replied discussion-style to the compose ask and died).
                # TWO bounded reminders per owed commitment (mechanical, confound-
                # excluded), then retire for real. One was not enough: the 2026-07-08
                # LOW rep00 integrator narrated "<submit_results>" as prose, took its one
                # nudge, verified with run_python, narrated "Now I'll submit" — and was
                # retired one turn short of the tool call, killing the cell.
                st[f"_prose_nudges:{owed}"] = nudges + 1
                last_event = await rs.spine.emit_event(
                    "intervention.recorded", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                    caused_by=last_event,
                    payload={"kind": "submit_reminder", "class": "mechanical",
                             "owed": owed, "attempt": nudges + 1, "max": 2})
                if nudges == 0:
                    text = ("(Your submission is still owed and nothing was submitted. "
                            "Writing it out as text is NOT a submission. Do the work in "
                            "this loop and submit it via the submit_results tool now.)")
                else:
                    text = ("(FINAL reminder: nothing has been submitted and the run ends "
                            "after this turn. Call the submit_results tool with your "
                            "package NOW, before any other output.)")
                msgs.append(NeutralMessage("user", [NeutralBlock(
                    kind=BlockKind.TEXT.value, text=text)]))
                return ActionPlan(result="continue", last_event_id=last_event)
            return ActionPlan(result="retire", last_event_id=last_event)  # model chose to end without a tool call

        tool_result_blocks: list[NeutralBlock] = []
        submitted = False
        handoffs = []
        turn_controls: list[str] = []
        expected_binding = request_binding
        for tu in tool_uses:
            # An accepted submit can advance the binding while this response
            # still has tools left. Check the new duty before accepting another
            # submission; give every requested tool its paired result.
            if (tu.tool_name == "submit_results" and readiness_gate is not None
                    and not readiness_gate()):
                denied = await rs.spine.emit_event(
                    "tool.denied", agent_id=agent.agent_id, turn_id=ctx.turn_id,
                    caused_by=last_event,
                    payload={"tool_name": tu.tool_name, "reason": "submission_not_ready",
                             "commitment_id": tool_context.submit_commitment_id})
                tr = ToolResult(
                    text="Submission not accepted: the current duty is not ready. "
                         "Wait for its prerequisites and notices before submitting.",
                    event_id=denied)
            else:
                tr = await dispatch_tool(
                    tu.tool_name, tu.arguments or {}, tool_context,
                    turn_id=ctx.turn_id, caused_by=last_event,
                    **({"expected_commitment_id": expected_binding}
                       if tu.tool_name == "submit_results" else {}),
                )
            tool_result_blocks.append(NeutralBlock(
                kind=BlockKind.TOOL_RESULT.value, tool_call_id=tu.tool_call_id, text=tr.text))
            if tr.event_id:
                last_event = tr.event_id
            if getattr(tr, "turn_control", None):
                turn_controls.append(tr.turn_control)
            if tr.submitted:
                # Only this response's own accepted submission may advance its
                # expected binding. A peer's change while the model was thinking
                # must not redirect a stale answer into a different case.
                expected_binding = tr.next_commitment_id or expected_binding
            if tr.submitted and post_submit_messages is not None:
                # Capture each commitment's transfer before the next tool can
                # overwrite last_submitted_commitment_id. Bind its cause now,
                # so an earlier transfer does not acquire a later submission.
                handoffs.extend(replace(msg, caused_by_event_id=last_event)
                                for msg in post_submit_messages())
            submitted = submitted or tr.submitted
        msgs.append(NeutralMessage("tool", tool_result_blocks))

        # Lifecycle actions (M8 §2): a registered action may end the turn (wait) or
        # the agent (retire) once its result is on the record. Retire wins.
        if any(tc == "retire" for tc in turn_controls):
            return ActionPlan(result="retire", messages=handoffs, last_event_id=last_event)
        if any(tc == "finish_turn" for tc in turn_controls):
            return ActionPlan(result="finish_turn", messages=handoffs, last_event_id=last_event)

        if submitted:
            # Emit the formal handoff to the next role (if any) on the way out, so the
            # downstream agent's readiness_gate opens and it sees this payload (§11/§12).
            if retire_after_submit is None or retire_after_submit():
                return ActionPlan(result="retire", messages=handoffs, last_event_id=last_event)  # outcome closes via on_close
            if continue_after_submit is not None and continue_after_submit():
                # Clocked megabatching (density calibration, 2026-08-15): the
                # binding advanced to a fresh, ACTIONABLE duty and the day is
                # not over — stay in the turn so the role can keep working.
                # Without this branch the engine ended every turn at one commit
                # and the per-turn batch rate was apparatus-forced, not chosen.
                return ActionPlan(result="continue", messages=handoffs, last_event_id=last_event)
            # A non-final stage (D9 draft/report): yield alive. The scheduler's dynamic
            # readiness withholds admission until the platform advances the submit binding
            # (no busy-spin); the next stage's inputs arrive as folded handoffs.
            return ActionPlan(result="finish_turn", messages=handoffs, last_event_id=last_event)
        return ActionPlan(result="continue", last_event_id=last_event)  # → next engine action (next iteration)

    async def closing_call(st: dict, instruction: str, *, spine, caused_by: str | None = None) -> dict:
        """One model call after the work period, on the agent's context as it stands, without tools (informal
        workarounds handover notes, design §4.3, October 28, 2026). It draws on the ledger's closing reserve, and
        no call ceiling applies. The context is copied, so the agent's own conversation is unchanged. Returns
        ``{"text", "outcome", "response_event_id"}``; the outcome is ``written``, ``empty``, ``tool_call``,
        ``refusal``, ``cap``, ``not_started`` or ``error``, and the text is set only when written."""
        msgs = list(st.get("messages") or [])
        if not msgs:
            return {"text": None, "outcome": "not_started", "response_event_id": None}
        if msgs[-1].role == "assistant" and _has_tool_use(msgs[-1]):
            msgs.pop()   # a call whose tools had not run when the work ended
        inbox, consumed = st.get("inbox_text", ""), st.get("inbox_consumed", 0)
        if len(inbox) > consumed:   # what reached the agent after its last call, as its next turn would show it
            msgs.append(NeutralMessage("user", [NeutralBlock(
                kind=BlockKind.TEXT.value, text=f"{inbox_heading or INBOX_HEAD}\n{inbox[consumed:]}")]))
        msgs.append(NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text=instruction)]))
        req = ModelRequest(call_id=new_ulid(), model_ref=model_ref, messages=msgs, tools=[],
                           sampling=SamplingParams(max_output_tokens=max_output_tokens, temperature=temperature),
                           reasoning=ReasoningRequest(kind=reasoning_kind, budget_tokens=reasoning_budget),
                           cache=_CACHE)
        try:
            resp = await call_model_gateway(
                req=req, adapter=adapter, ledger=ledger, spine=spine, raw_store=raw_store,
                activity_class=activity_class, exposure_contract=exposure_contract, confirmatory=confirmatory,
                agent_id=tool_context.agent_id, caused_by=caused_by, closing_call=True)
        except CostCapWouldBreach:
            return {"text": None, "outcome": "cap", "response_event_id": None}
        except Exception as exc:  # noqa: BLE001 — a failed note is recorded, never a failed run
            return {"text": None, "outcome": "error", "error": repr(exc), "response_event_id": None}
        event = getattr(resp, "response_event_id", None)
        if resp.stop_reason == "refusal":
            return {"text": None, "outcome": "refusal", "response_event_id": event}
        if any(b.kind == BlockKind.TOOL_USE.value for b in resp.content_blocks):
            return {"text": None, "outcome": "tool_call", "response_event_id": event}
        text = "".join(b.text or "" for b in resp.content_blocks if b.kind == BlockKind.TEXT.value).strip()
        return {"text": text or None, "outcome": "written" if text else "empty", "response_event_id": event}

    def reserve_closing_call() -> float | None:
        """Reserve, in the ledger's dollar cap, the most this agent's closing call can be projected to cost: a
        context half again its budget (the context grows past the budget between compactions) and a full output.
        Returns the amount, or None without a context budget (nothing is reserved)."""
        if context_budget_tokens is None:
            return None
        n = int(context_budget_tokens * 1.5)
        row = ledger.pricing_table.price(model_ref).for_prompt(n)
        usd = (n * row.input + max_output_tokens * row.output) / 1e6
        ledger.closing_reserve_usd = float(ledger.closing_reserve_usd or 0.0) + usd
        return usd

    _ps = getattr(tool_context, "protocol_state", None)
    if isinstance(_ps, dict):   # a procedure may ask for closing calls (for example, handover notes)
        _ps["closing_call"] = closing_call
        _ps["reserve_closing_call"] = reserve_closing_call
    return behave
