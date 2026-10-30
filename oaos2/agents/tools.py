"""Check and execute the common tools available to model agents.

The host checks tool permission, path containment, and file access before acting.
write_file records a workspace write; read_file records an allowed read;
run_python stages code in private scratch and runs it in the agent's container.
submit_results checks the payload and calls OutcomeCoordinator.commit, which
accepts an official decision and closes the outcome only when its contract is met.

Containers cannot write the submitted area directly. Provider credentials stay
on the host. Container network access follows DockerPolicy; it is disabled by
default, not unconditionally absent. See docs/SYSTEM.md and docs/RUNBOOK.md."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from oaos2.docker.isolation import IsolationViolation
from oaos2.docker.runner import run_tool_in_container
from oaos2.models.types import ToolSpec
from oaos2.outcomes.conformance import CommitmentConformanceError, check_conformance
from oaos2.ulid import new_ulid
from oaos2.workspace.acl import FileAccessPolicy, Zone
from oaos2.workspace.hashing import hash_bytes
from oaos2.workspace.zones import ZoneClass

# Neutral ToolSpecs the adapter renders to the provider schema (M3 §2). Served to EVERY
# pack (the runner filters by role), so the descriptions must stay task-neutral — a
# dataset example from one pack would gaslight another pack's agents about their run.
BUILTIN_TOOL_NAMES: frozenset[str] = frozenset(
    {"run_python", "read_file", "write_file", "submit_results"})

PAPER_TOOLSPECS: list[ToolSpec] = [
    ToolSpec(
        name="run_python",
        description=(
            "Run a Python 3 script in your sandbox. The task's data files (if any) are "
            "read-only under /visible/data/. Your working directory is writable (relative "
            "paths land there). numpy, pandas, scipy, statsmodels, scikit-learn are "
            "installed. Returns stdout and stderr. Print the values you need to inspect."
        ),
        parameters_schema={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python source to execute."}},
            "required": ["code"],
        },
    ),
    ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file. Use 'data/<name>.csv' for inputs, or a path you wrote.",
        parameters_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="write_file",
        description="Write a UTF-8 text file into your working directory (e.g. a reusable script).",
        parameters_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    ),
    ToolSpec(
        name="submit_results",
        description=(
            "Submit your final results as a JSON object matching the submission shape your "
            "task instructions specify. This ends the task. Submit EVERYTHING required in one call."
        ),
        parameters_schema={
            "type": "object",
            "properties": {"results": {"type": "object", "description": "result_name -> value"}},
            "required": ["results"],
        },
    ),
]

def apply_tool_descriptions(toolspecs: list, overrides: dict) -> list:
    """Return ``toolspecs`` with the descriptions a pack declares for built-in tools.

    The generic descriptions above were written for the analysis tasks ("This ends the
    task", "Use 'data/<name>.csv'") and contradicted the budget task's packets, in which a
    role submits one duty after another and reads a store by its index (realism review
    2026-09-25). A pack states the text once in its manifest; it is identical for every
    role and arm. Names not in ``overrides`` keep the generic text; the schema never changes."""
    if not overrides:
        return list(toolspecs)
    return [ToolSpec(name=t.name, description=overrides[t.name], parameters_schema=t.parameters_schema)
            if t.name in overrides else t for t in toolspecs]


_STDOUT_CAP = 8000
_READ_CAP = 20000
_TOOL_OUTPUT_CAP = 6000  # cap on the observation text persisted to the spine
_CONTAINER_SCRATCH = "/work/agents/{agent_id}"


@dataclass
class ToolContext:
    """Everything the host needs to execute one agent's tools."""

    agent_id: str
    rs: object  # RuntimeState (spine + workspace)
    backend: object  # ContainerBackend
    handle: object  # ContainerHandle for this agent
    run_dir: object  # RunDir
    coordinator: object  # OutcomeCoordinator
    submit_commitment_id: str
    # The contract's FINAL scored commitment (set at construction): calls made while the
    # agent's binding equals this id are exempt from the token pool's final-stage
    # reserve (pricing.ledger.CostLedger.final_reserve_tokens).
    final_commitment_id: str | None = None
    wall_clock_cap: int = 180
    # A per-call limit on `run_python`, enforced inside the sandbox (`timeout`), after which the script is stopped and
    # the agent told so; None leaves only `wall_clock_cap`. PC1, October 15, 2026: with the cap at the container's
    # lifetime, one laboratory's script ran from minute 2.7 to the end of the run, and the laboratory never acted again.
    python_timeout_s: int | None = None
    exec_count: int = 0
    submit_retries: int = 0  # bounded retry counter for the submit-time conformance gate
    submit_intervention_ids: list = field(default_factory=list)  # nonconformance retries, threaded into the commit's caused_by
    submit_conformance_failure: CommitmentConformanceError | None = None
    # The binding may advance inside OutcomeCoordinator.on_commit before the model
    # behavior emits its post-submit handoff.  Preserve the commitment that actually
    # crossed the single-writer boundary so staged routing never labels/sends the next
    # (not-yet-submitted) slot instead.
    last_submitted_commitment_id: str | None = None
    allowed_tools: set | None = None  # per-role tool allow-list (DESIGN §18.1); None = all.
                                      # HARD-enforced at dispatch (not just offer-layer), so a
                                      # role cannot use a tool it wasn't granted even if it tries.
    # Optional software-layer ACL (M4 §1, DESIGN §9). When present it is checked
    # at dispatch (belt-and-suspenders over the M2 OS mount enforcement); a denied
    # read/write/execute is emitted as tool.denied, never a silent drop. When None
    # (the foundation paper-replication packs), only OS enforcement applies.
    file_access_policy: FileAccessPolicy | None = None
    # When set, the host-side disk-quota monitor runs after each sandbox exec
    # (M2 §8.3) and fails the run on breach.
    disk_limit: str | None = None
    # The submitting role's authority (M5 §18.1, DESIGN §13). When set and the role
    # lacks ``may_submit_milestones``, submit is refused as a protocol.violation before
    # any commit. None (the four decomposition-only arms) ⇒ permissive.
    decision_rights: object | None = None  # decision_rights.DecisionRights
    # Registered task actions offered to THIS role (M8 §2): name -> TaskAction.
    # None = the pack declares none. Grant-checked at dispatch like built-ins.
    task_actions: dict | None = None
    # Per-agent state a coordination procedure attaches (pool membership, wait
    # flags, attempt counters). The engine never reads it.
    protocol_state: dict = field(default_factory=dict)
    # Async callables ``(ctx, *, turn_id, caused_by)`` a coordination procedure attaches to
    # run inside the agent's own turn just before its code executes or it reads a file, so
    # procedure-kept files in the agent's scratch (the materials lab's records file) are
    # current when the agent's analysis loads them. The engine never adds any.
    before_exec: list = field(default_factory=list)
    # Async callables ``(ctx, results, commitment) -> str | None`` a coordination procedure
    # attaches to run inside submit_results before the conformance gate; a returned string
    # refuses the submission with that reason (a tool.denied, never a nonconformance retry).
    # The budget exchange's assent rule is the first use (2026-09-25).
    submit_prechecks: list = field(default_factory=list)

    def advance_submit_binding(self, commitment_id: str) -> None:
        """Advance to the next owed commitment with a FRESH conformance-retry budget.

        D9 staged composition reuses one agent for draft→final (or report→comment), but
        ``submit_retries`` counted per agent lifetime: a draft that burned both retries
        left the final with zero, so its first infeasible attempt went straight to
        nonconformant-accept (2026-07-08 organic rep05: $389 final, scored 0.0). The
        retry budget and the caused_by intervention thread are per-commitment."""
        self.submit_commitment_id = commitment_id
        self.submit_retries = 0
        self.submit_intervention_ids = []


@dataclass
class ToolResult:
    text: str
    submitted: bool = False
    event_id: str | None = None  # the tool.result event (for causal chaining)
    next_commitment_id: str | None = None  # binding immediately after this acceptance
    # Lifecycle actions (M8 §2 wait/retire): None = ordinary tool; "finish_turn"
    # ends the agent's turn after this tool's result is recorded; "retire" ends
    # the agent. The model loop honors it after appending the tool results.
    turn_control: str | None = None


def _scratch_zone(agent_id: str) -> Zone:
    return Zone(name=f"scratch_{agent_id}", zone_class=ZoneClass.AGENT_WRITABLE.value, is_shared=False)


def _visible_zone() -> Zone:
    return Zone(name="visible", zone_class=ZoneClass.TASK_VISIBLE.value, is_shared=False)


def _contained(root: Path, rel: str) -> Path | None:
    """Map an agent-supplied path onto ``root``; None if it resolves outside.

    The tool boundary is where agent-controlled paths enter host-side I/O:
    ``..`` segments, absolute paths, or a symlink planted in scratch would
    otherwise reach ``trace/`` (M1 single-writer), ``submitted/`` (M6 sole
    committer via ``commit()``), or the pack's hidden assets. Fail-closed.
    """
    target = Path(root) / rel
    root_real = os.path.realpath(root)
    target_real = os.path.realpath(target)
    if target_real != root_real and not target_real.startswith(root_real + os.sep):
        return None
    return target


async def _deny(ctx: "ToolContext", tool_name: str, reason: str, *, turn_id: str, caused_by: str) -> "ToolResult":
    """Emit tool.denied for a software-ACL violation and return an error result
    the model can read (M4 §1, §8 — a denial is first-class, never a silent drop)."""
    denied = await ctx.rs.spine.emit_event(
        "tool.denied", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
        payload={"tool_name": tool_name, "reason": reason, "enforcement": "software"},
    )
    return ToolResult(text=f"Error: access denied ({reason})", event_id=denied)


async def dispatch_tool(tool_name: str, args: dict, ctx: ToolContext, *, turn_id: str, caused_by: str,
                        expected_commitment_id: str | None = None) -> ToolResult:
    rs = ctx.rs
    # A registered task action records its FULL arguments on the call event (M8
    # §2): attempts, posts and reports are auditable from the trace alone. Built-in
    # tools keep their existing call record.
    action = (ctx.task_actions or {}).get(tool_name)
    called = await rs.spine.emit_event(
        "tool.called", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
        payload=({"tool_name": tool_name, "action": True,
                  "effect_class": action.effect_class, "arguments": dict(args or {})}
                 if action is not None else {"tool_name": tool_name}),
    )
    # HARD per-role tool gate (DESIGN §18.1, §8): reject a tool the role wasn't granted,
    # even if the model emits it — offer-layer omission alone is not enforcement.
    if ctx.allowed_tools is not None and tool_name not in ctx.allowed_tools:
        denied = await rs.spine.emit_event(
            "tool.denied", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=called,
            payload={"tool_name": tool_name, "reason": "tool_not_permitted_for_role"},
        )
        return ToolResult(text=f"Error: tool {tool_name!r} is not permitted for your role.", event_id=denied)
    try:
        if tool_name == "run_python":
            res = await _run_python(args.get("code", ""), ctx, turn_id=turn_id, caused_by=called)
        elif tool_name == "read_file":
            res = await _read_file(args.get("path", ""), ctx, turn_id=turn_id, caused_by=called)
        elif tool_name == "write_file":
            res = await _write_file(args.get("path", ""), args.get("content", ""), ctx, turn_id=turn_id, caused_by=called)
        elif tool_name == "submit_results":
            res = await _submit(args.get("results", {}), ctx, turn_id=turn_id, caused_by=called,
                                expected_commitment_id=expected_commitment_id)
        elif action is not None:
            res = await action.handler(dict(args or {}), ctx, turn_id=turn_id, caused_by=called)
        else:
            denied = await rs.spine.emit_event(
                "tool.denied", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=called,
                payload={"tool_name": tool_name, "reason": "unknown_tool"},
            )
            return ToolResult(text=f"Error: unknown tool {tool_name!r}", event_id=denied)
    except (IsolationViolation, CommitmentConformanceError):
        # A disk-quota / isolation breach is run-fatal (M2 §8.3): it must propagate
        # to fail the run, NOT be handed back to the model as a recoverable error.
        raise
    except Exception as exc:  # noqa: BLE001 — surface tool errors to the model, never crash the run
        return ToolResult(text=f"Error executing {tool_name}: {exc}")
    # Capture the OUTPUT the agent observed (run_python stdout/stderr, file content,
    # submit confirmation) on the spine — not just the exit code — so the
    # observation→reasoning→decision chain is reconstructable (DESIGN §9).
    result_event = await rs.spine.emit_event(
        "tool.result", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=res.event_id or called,
        payload={"tool_name": tool_name, "submitted": res.submitted,
                 "output": (res.text or "")[:_TOOL_OUTPUT_CAP]},
    )
    res.event_id = result_event
    return res


async def _run_python(code: str, ctx: ToolContext, *, turn_id: str, caused_by: str) -> ToolResult:
    zone = _scratch_zone(ctx.agent_id)
    if ctx.file_access_policy is not None:
        # run_python both WRITES the script and EXECUTES it in the scratch zone.
        if not ctx.file_access_policy.may_write(zone.name):
            return await _deny(ctx, "run_python", f"write_denied:{zone.name}", turn_id=turn_id, caused_by=caused_by)
        if not ctx.file_access_policy.may_execute(zone.name):
            return await _deny(ctx, "run_python", f"execute_denied:{zone.name}", turn_id=turn_id, caused_by=caused_by)
    for hook in ctx.before_exec:
        await hook(ctx, turn_id=turn_id, caused_by=caused_by)
    ctx.exec_count += 1
    name = f"_exec_{ctx.exec_count}.py"
    scratch = ctx.run_dir.ensure_agent_scratch(ctx.agent_id)
    # Write the script host-side (captured via M4) so the container sees it through the bind mount.
    await ctx.rs.workspace.capture_write(
        agent_id=ctx.agent_id, path=scratch / name, new_bytes=code.encode(),
        zone=_scratch_zone(ctx.agent_id), tool_call_event_id=caused_by, turn_id=turn_id,
        new_scratch_script=True,
    )
    scratch_container = _CONTAINER_SCRATCH.format(agent_id=ctx.agent_id)
    # Run from the writable scratch dir (the image WORKDIR is read-only) so the
    # script's relative writes land in scratch; data is read-only at /visible/data.
    # Wrap the exec in M4's scratch-scoped before/after scan so any files the script
    # CREATES become FileChange(hash_scan) events on the spine — not just physical
    # bytes copied to captured/ at teardown (M4 §3; closes the lineage gap).
    holder: dict = {}

    async def _exec() -> None:
        holder["res"] = await run_tool_in_container(
            ctx.rs.spine, ctx.backend, ctx.handle, tool_call_id=new_ulid(),
            argv=["sh", "-lc", f"cd {scratch_container} && " + (
                f"timeout -k 5 {int(ctx.python_timeout_s)} python {name}" if ctx.python_timeout_s else f"python {name}")],
            wall_clock_cap=ctx.wall_clock_cap, caused_by=caused_by, disk_limit=ctx.disk_limit,
        )

    await ctx.rs.workspace.execute_with_capture(
        agent_id=ctx.agent_id, scratch_root=scratch, run_execute=_exec,
        tool_call_event_id=caused_by, zone=_scratch_zone(ctx.agent_id), turn_id=turn_id,
    )
    res = holder["res"]
    out = (res.stdout or "")[:_STDOUT_CAP]
    err = (res.stderr or "")[-2000:]
    parts = [f"exit_code={res.exit_code}"]
    if res.timed_out:
        parts.append("(timed out)")
    if ctx.python_timeout_s and res.exit_code in (124, 137):
        parts.append(f"(stopped: the script ran longer than {int(ctx.python_timeout_s)} seconds, the limit for one call)")
    if out:
        parts.append(f"stdout:\n{out}")
    if err:
        parts.append(f"stderr:\n{err}")
    return ToolResult(text="\n".join(parts))


async def _read_file(path: str, ctx: ToolContext, *, turn_id: str, caused_by: str) -> ToolResult:
    for hook in ctx.before_exec:
        await hook(ctx, turn_id=turn_id, caused_by=caused_by)
    # Accept logical paths ("data/x") AND absolute container paths the agent may use
    # in-sandbox ("/visible/data/x", "/work/agents/{id}/x") — map them to the host.
    rel = path
    scratch_prefix = _CONTAINER_SCRATCH.format(agent_id=ctx.agent_id)
    if rel.startswith("/visible/"):
        rel = rel[len("/visible/"):]
    elif rel.startswith(scratch_prefix + "/"):
        rel = rel[len(scratch_prefix) + 1:]
    candidates = [
        (ctx.run_dir.visible, _visible_zone()),
        (ctx.run_dir.agent_scratch(ctx.agent_id), _scratch_zone(ctx.agent_id)),
    ]
    for root, zone in candidates:
        p = _contained(root, rel)
        if p is None:  # escapes every granted zone → recorded denial, never a probe result
            return await _deny(ctx, "read_file", f"path_escapes_zone:{zone.name}",
                               turn_id=turn_id, caused_by=caused_by)
        if p.is_file():
            if ctx.file_access_policy is not None and not ctx.file_access_policy.may_read(zone.name):
                return await _deny(ctx, "read_file", f"read_denied:{zone.name}", turn_id=turn_id, caused_by=caused_by)
            raw = p.read_bytes()
            data = raw.decode(errors="replace")
            # Record the read as a first-class FileEvent with the content hash, so
            # the "who saw what" half of the lineage chain is queryable (DESIGN §9).
            await ctx.rs.spine.emit_event(
                "file.read", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
                payload={
                    "path": str(path), "zone": zone.name, "operation": "read",
                    # Same prefixed form as FileChange/ArtifactVersion/StateCommitment
                    # hashes (hash_bytes), so the read-vs-write lineage join matches.
                    "content_hash": hash_bytes(raw), "size_bytes": len(raw),
                },
            )
            truncated = len(data) > _READ_CAP
            return ToolResult(text=data[:_READ_CAP] + ("\n...[truncated]" if truncated else ""))
    return ToolResult(text=f"Error: file not found: {path}")


async def _write_file(path: str, content: str, ctx: ToolContext, *, turn_id: str, caused_by: str) -> ToolResult:
    zone = _scratch_zone(ctx.agent_id)
    if ctx.file_access_policy is not None and not ctx.file_access_policy.may_write(zone.name):
        return await _deny(ctx, "write_file", f"write_denied:{zone.name}", turn_id=turn_id, caused_by=caused_by)
    scratch = ctx.run_dir.ensure_agent_scratch(ctx.agent_id)
    # Accept the container-absolute spelling of the agent's own scratch (as _read_file does).
    rel = path
    scratch_prefix = _CONTAINER_SCRATCH.format(agent_id=ctx.agent_id)
    if rel.startswith(scratch_prefix + "/"):
        rel = rel[len(scratch_prefix) + 1:]
    target = _contained(scratch, rel)
    if target is None:
        return await _deny(ctx, "write_file", f"path_escapes_zone:{zone.name}",
                           turn_id=turn_id, caused_by=caused_by)
    await ctx.rs.workspace.capture_write(
        agent_id=ctx.agent_id, path=target, new_bytes=content.encode(),
        zone=_scratch_zone(ctx.agent_id), tool_call_event_id=caused_by, turn_id=turn_id,
    )
    return ToolResult(text=f"wrote {path}")


async def _submit(results: dict, ctx: ToolContext, *, turn_id: str, caused_by: str,
                  expected_commitment_id: str | None = None) -> ToolResult:
    if expected_commitment_id is not None and expected_commitment_id != ctx.submit_commitment_id:
        denied = await ctx.rs.spine.emit_event(
            "tool.denied", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
            payload={"tool_name": "submit_results", "reason": "submission_binding_changed",
                     "expected_commitment_id": expected_commitment_id,
                     "current_commitment_id": ctx.submit_commitment_id},
        )
        return ToolResult(text="Submission not accepted: your assigned decision changed while "
                          "this response was being prepared. Read the new duty before submitting.",
                          event_id=denied)
    if not isinstance(results, dict):
        return ToolResult(text="Error: results must be a JSON object of result_name -> value")

    # A turn opened for something other than the role's duty (a pending query to answer)
    # may not submit that duty: ``protocol_state["submission_hold"]`` is a callable set by
    # the procedure that returns the reason while the hold applies (2026-09-25).
    hold = ctx.protocol_state.get("submission_hold")
    hold_reason = hold() if callable(hold) else None
    if hold_reason:
        ev = await ctx.rs.spine.emit_event(
            "tool.denied", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
            payload={"tool_name": "submit_results", "reason": "submission_hold",
                     "commitment_id": ctx.submit_commitment_id, "detail": hold_reason})
        return ToolResult(text=f"Submission not accepted: {hold_reason}", event_id=ev)

    # Submit authority (M5 §18.1, DESIGN §13): a role without ``may_submit_milestones``
    # may not close a milestone — refuse before committing (a protocol.violation, never a
    # silent drop). Permissive when no decision rights are declared (the four arms).
    if ctx.decision_rights is not None and not ctx.decision_rights.can_submit():
        ev = await ctx.rs.spine.emit_event(
            "protocol.violation", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
            payload={"reason": "submit_without_authority", "commitment_id": ctx.submit_commitment_id},
        )
        return ToolResult(text="Error: this role is not authorized to submit milestones.",
                          submitted=False, event_id=ev)

    # Submit-time conformance gate (DESIGN §13 / M7 §2.1): validate the payload SHAPE
    # declared on the commitment BEFORE committing. On non-conformance, refuse and return
    # structural feedback (shape only — no answer values, so it stays inside the
    # public-feedback whitelist) so the model loop corrects and resubmits; bounded retries,
    # each a recorded Intervention threaded into causality; exhaustion invalidates the
    # cell because the declared apparatus was not instantiated.
    commitment = ctx.coordinator.contract.commitment(ctx.submit_commitment_id)
    fmt = getattr(commitment, "submission", {}) or {}
    # Envelope normalization (calibration round 2, 2026-08-12): a model sometimes wraps
    # the payload under its own slot id — {"results": {"<commitment_id>": {...}}} —
    # which then fails `required` with the actively misleading "missing field(s)"
    # (the fields exist one level deeper). The wrapper names the slot explicitly, so
    # unwrapping is unambiguous transport normalization, identical across arms; the
    # raw capture retains what the model sent.
    if (set(results.keys()) == {ctx.submit_commitment_id}
            and isinstance(results[ctx.submit_commitment_id], dict)):
        results = results[ctx.submit_commitment_id]
    # Cross-commitment context for the disposal gate (D-v2.2): committed payloads only —
    # the gate checks disposition COVERAGE of already-committed amendments, never values.
    committed_payloads = {cid: ctx.coordinator.payloads.get(cid, {})
                          for cid in ctx.coordinator.committed}
    # Slot-addressed envelopes (clocked calibration, 2026-08-15): models that
    # fall behind, or that megabatch a backlog, submit payloads keyed by slot id
    # — one foreign slot ("finish the case the platform already closed") or a
    # bundle of several dispositions in one call. The bare "missing field(s)"
    # feedback never said why that fails; name the situation and the remedy
    # instead of shape-checking the envelope against the current slot's format.
    def _is_slot(key: str) -> bool:
        try:
            ctx.coordinator.contract.commitment(key)
        except Exception:  # noqa: BLE001 — not a commitment id
            return False
        return True

    wrong_slot = None
    slot_keys = [k for k in results
                 if isinstance(results[k], dict) and _is_slot(k)]
    # Guard against field/slot name collisions (the organic draft_allocation
    # payload carries top-level FIELDS named like commitments): a payload that
    # supplies any of the current slot's own required fields is a payload, not
    # a slot-addressed envelope.
    required_now = set((fmt or {}).get("required") or [])
    if (slot_keys and len(slot_keys) == len(results)
            and not (set(results) & required_now)):
        if len(slot_keys) > 1:
            wrong_slot = (
                f"your payload bundles several slots ({', '.join(sorted(slot_keys))}). "
                "Submit ONE slot per submit_results call — your currently "
                f"authorized slot is {ctx.submit_commitment_id!r}; you may call "
                "submit_results several times in one turn to clear a backlog, "
                "and the platform announces each next slot as the previous one "
                "commits")
        elif slot_keys[0] != ctx.submit_commitment_id:
            wrapper_key = slot_keys[0]
            state = ("already closed — the platform or another role committed "
                     "it; it needs nothing further from you"
                     if wrapper_key in ctx.coordinator.committed
                     else "not your currently authorized slot")
            wrong_slot = (
                f"your payload addresses slot {wrapper_key!r}, which is "
                f"{state}. Your currently authorized submission is "
                f"{ctx.submit_commitment_id!r} — submit that slot's payload "
                "(see its duty notice), not a wrapper naming another slot")
    if wrong_slot is not None:
        ok, problems = False, [wrong_slot]
    else:
        for precheck in ctx.submit_prechecks:
            refusal = await precheck(ctx, results, commitment)
            if refusal:
                ev = await ctx.rs.spine.emit_event(
                    "tool.denied", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
                    payload={"tool_name": "submit_results", "reason": "submit_precheck",
                             "commitment_id": ctx.submit_commitment_id, "detail": refusal})
                return ToolResult(text=f"Submission not accepted: {refusal}.", event_id=ev)
        ok, problems = check_conformance(results, fmt, committed=committed_payloads,
                                         commitment=commitment)
    commit_cause = caused_by
    if not ok:
        max_retries = int(fmt.get("max_retries", 2))
        if ctx.submit_retries < max_retries:
            ctx.submit_retries += 1
            iv = await ctx.rs.spine.emit_event(
                "intervention.recorded", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
                payload={"kind": "submission_nonconformant_retry", "class": "recorded",
                         "attempt": ctx.submit_retries, "max_retries": max_retries, "problems": problems},
            )
            ctx.submit_intervention_ids.append(iv)
            feedback = (f"Submission not accepted (attempt {ctx.submit_retries}/{max_retries}). "
                        "Fix the following and call submit_results again:\n- " + "\n- ".join(problems))
            return ToolResult(text=feedback, submitted=False, event_id=iv)
        # Exhaustion means the cell no longer instantiates its declared apparatus.
        # Abort rather than laundering treatment failure into a low outcome score.
        rejected = await ctx.rs.spine.emit_event(
            "intervention.recorded", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
            payload={"kind": "submission_nonconformant_rejected", "class": "treatment_defining",
                     "commitment_id": ctx.submit_commitment_id, "problems": problems},
        )
        ctx.submit_intervention_ids.append(rejected)
        ctx.submit_conformance_failure = CommitmentConformanceError(
            ctx.submit_commitment_id, problems)
        raise ctx.submit_conformance_failure

    # The commit lists any nonconformance interventions as causal antecedents (multi-parent
    # caused_by), so the assisted/unassisted walk sees the correction feedback that shaped
    # the final submission (DESIGN §13 §3.3). A clean first-try submit lists only its cause.
    causes = [commit_cause, *ctx.submit_intervention_ids]
    submitted_commitment_id = ctx.submit_commitment_id
    sc = await ctx.coordinator.commit(
        commitment_id=submitted_commitment_id, payload=results,
        agent_id=ctx.agent_id, session_id=f"s_{ctx.agent_id}",
        caused_by=list(dict.fromkeys(causes)),  # dedup, preserve order
    )
    if sc is None:
        return ToolResult(text="Error: submission refused (already submitted or blocked).")
    ctx.last_submitted_commitment_id = submitted_commitment_id
    # Clocked runs: hand the next duty over INLINE so a role with time left in
    # the day can keep working. Without this the confirmation read "Task
    # complete." and every live agent stopped at one slot per turn — the
    # megabatch escape valve from the lane-arithmetic bound existed
    # mechanically but the apparatus text itself closed it (density
    # calibration, 2026-08-15). Batched runs keep the legacy text.
    next_duty = ""
    clock = getattr(ctx.rs, "clock", None) if ctx.rs is not None else None
    if (clock is not None
            and ctx.submit_commitment_id != submitted_commitment_id
            and ctx.submit_commitment_id not in ctx.coordinator.committed):
        nxt = ctx.coordinator.contract.commitment(ctx.submit_commitment_id)
        required = list((nxt.submission or {}).get("required", []))
        note = str((nxt.submission or {}).get("duty_note") or "").strip()
        from oaos2.outcomes.conformance import duty_cap_note
        next_duty = (
            f" Your next authorized submission is `{ctx.submit_commitment_id}`."
            + (f" Required top-level JSON fields: {', '.join(required)}."
               if required else "")
            + (f" {note}" if note else "")
            + duty_cap_note(nxt.submission)
            + " If you have what you need, you may submit it in this same "
            "turn; otherwise stop here — unfinished duties carry into the "
            "next day.")
        builder = getattr(ctx.rs, "case_file_builder", None)
        if builder is not None:
            case_file = builder(ctx.submit_commitment_id, ctx.agent_id)
            if case_file:
                next_duty += "\n" + case_file
    elif clock is None:
        next_duty = " Task complete."
    return ToolResult(text=f"Submitted `{submitted_commitment_id}`.{next_duty}",
                      submitted=True,
                      next_commitment_id=ctx.submit_commitment_id,
                      event_id=ctx.coordinator.committed_event_ids[submitted_commitment_id])
