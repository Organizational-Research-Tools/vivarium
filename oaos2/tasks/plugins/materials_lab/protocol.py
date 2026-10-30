"""The materials lab coordination procedure, mode ``materials_lab``: binds each role to
its credit slots, attaches the pool and the board to every role's tool context, gates
admission while a role waits, renders results and messages into the next turn, and
runs the pool's dispatch and finalization beside the agent loops."""

from __future__ import annotations

from oaos2.communication.board import Board, open_topic
from oaos2.communication.mailbox import MailboxItem
from oaos2.experiments.coordination.base import (
    CoordinationContext,
    CoordinationProtocol,
    RoleHooks,
    register_coordination_protocol,
    role_commitment_seq,
)
from oaos2.kernel.runtime import _deliver
from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab.actions import _refresh_records_file
from oaos2.tasks.plugins.materials_lab.pool import LabPool
from oaos2.ulid import new_ulid

_RENDERED_KINDS = frozenset({"report_result", "project_closed", "project_standing", "board_post", "note", "challenge_result",
                             "audit_result"})


def start_note_text(pool: LabPool, agent_id: str, objective: str) -> str:
    """The start-of-run note a lab receives before its first turn. A function of its own so
    that the dashboard's situation page shows the text a run delivers, not a paraphrase."""
    instrument = ", ".join(L.PROPERTIES[i] for i in pool.instruments[agent_id])
    # The other operator of the same instrument, named where the coded presentation is on: in the
    # coded pair of September 26 several labs believed they were their instrument's only operator.
    twins = sorted({r for i in pool.instruments[agent_id] for r in pool.instruments_by_property(i)} - {agent_id})
    twin = (f"; {', '.join(twins)} operates it too" if twins and pool.pres.enabled else "")
    if pool.vocabulary:  # the testing firms' wording (supplier-k): written for them, then the net of vocabulary.py
        guide = ("Call firm_info for the design components and their settings, the design notes, the directory of "
                 "test bench operators, and the projects.")
    elif pool.pres.enabled:
        guide = ("Call lab_info for the modules and their variants, the formulation notes, the directory of instrument "
                 "owners, and the projects.")
    else:
        guide = "Call lab_info for the diagram, the directory of instrument owners, and the projects."
    return pool.say(f"[lab] You are {agent_id}; you operate the {instrument} instrument{twin}. "
            + (f"{objective} " if objective else "")
            + (f"{pool.processing_text} " if pool.processing_text else "")
            + (f"{pool.client_text} " if pool.client_text else "")
            + f"{pool.credit_text} "
            + (f"{pool.failure_text} " if pool.failure_text else "")
            + (f"{pool.feasible_text} " if pool.feasible_text else "")
            + (f"{pool.seed_text} " if pool.seed_text else "")
            + (f"{pool.scoring_text} " if pool.scoring_text else "")
            + (f"{pool.time_text()} " if pool.institution else "")
            + (f"{pool.urgency_for(agent_id)} " if pool.urgency_for(agent_id) else "")
            + (f"{pool.guidance_text} " if pool.guidance_text else "")
            + guide)


def validate_settings(spec) -> None:
    """The hook ``OrganizationSpec.validate`` calls: this plugin's settings check (settings.py)."""
    from oaos2.tasks.plugins.materials_lab.settings import validate_settings as check
    check(spec)


@register_coordination_protocol
class MaterialsLabProtocol(CoordinationProtocol):
    mode = "materials_lab"
    initial_duty_in_prompt = False

    def __init__(self) -> None:
        self._pool: LabPool | None = None
        self._board: Board | None = None

    def build_chain(self, org_spec, contract) -> list:
        chain = []
        for role in org_spec.roles:
            sequence = role_commitment_seq(org_spec, contract, role)
            if not sequence:
                raise ValueError(f"materials_lab role {role.role_id!r} has no credit slot in the contract")
            chain.append((role, sequence[0]))
        return chain

    def _ensure_pool(self, ctx: CoordinationContext) -> LabPool:
        if self._pool is None:
            self._pool = LabPool.from_context(ctx)
        return self._pool

    def _ensure_board(self, pool: LabPool) -> Board:
        if self._board is None:
            self._board = Board()
            self._board.configure(pool.board_settings)  # flat unless the preset asks for the forum form

            async def _on_delivered(agent_id: str, cause: str | None) -> None:
                await pool._wake(agent_id, "message", cause)

            self._board.on_delivered = _on_delivered
        return self._board

    def role_hooks(self, ctx: CoordinationContext, index: int, role, commit_id: str, tool_ctx) -> RoleHooks:
        pool = self._ensure_pool(ctx)
        tool_ctx.protocol_state["lab"] = pool
        if tool_ctx.allowed_tools is not None and "retire" not in tool_ctx.allowed_tools:
            # no retire action: a turn that ends without an action keeps the lab in the run, waiting
            tool_ctx.protocol_state["may_end_turn"] = lambda rid=role.role_id: pool.hold(rid)
        # records shared by another lab reach this role's records file before its next
        # script or file read, not only after its next lab action
        tool_ctx.before_exec.append(_refresh_records_file)
        self._ensure_board(pool).attach(tool_ctx)
        agent_id = role.role_id

        def readiness() -> bool:
            return not pool.is_waiting(agent_id) and pool.state != "finalized"

        def inbound(observations, st) -> None:
            texts = [str(o.get("payload")) for o in observations if o.get("kind") in _RENDERED_KINDS]
            if texts:
                st["inbox_text"] = "\n".join(filter(None, [st.get("inbox_text", ""), *texts])).strip()
            # A lab held after a turn without an action (``LabPool.hold``) resumes on new input. Should it ever
            # resume with none, its conversation would end on its own words; it is told the run continues.
            msgs = st.get("messages")
            if (msgs and getattr(msgs[-1], "role", None) == "assistant" and not pool.is_waiting(agent_id)
                    and pool.state != "finalized" and len(st.get("inbox_text", "")) <= st.get("inbox_consumed", 0)):
                st["inbox_text"] = (st.get("inbox_text", "") + "\n" + pool.say("[laboratory] The run continues.")).strip()

        hooks = RoleHooks()
        hooks.readiness = readiness
        hooks.inbound = inbound
        hooks.retire_after_submit = lambda: False
        hooks.continue_after_submit = lambda: True
        return hooks

    def make_on_start(self, ctx: CoordinationContext):
        pool = self._ensure_pool(ctx)

        async def orchestrate() -> None:
            # The presentation mapping (codes, order, units) goes on the researcher channel before
            # anything is shown, so the analysis can always read what the labs saw.
            await ctx.spine.emit_event("presentation.mapped", audience="researcher", payload=pool.pres.mapping())
            await pool.apply_seed()
            for tc in ctx.tc_by_role.values():
                instrument = ", ".join(L.PROPERTIES[i] for i in pool.instruments[tc.agent_id])
                objective = pool.objective_for(tc)
                await ctx.spine.emit_event(
                    "lab.staged", agent_id=tc.agent_id,
                    payload={"instrument": instrument, "instance_seed": pool.inst.seed,
                             "density": pool.inst.density, "family_density": dict(pool.inst.family_density),
                             "family_types": {f: list(t) for f, t in pool.inst.family_types.items()},
                             "capacity": pool.records.capacity,
                             "request_cap": pool.records.request_cap, "rival": pool.rival,
                             "known_feasible": list(pool.known_feasible),
                             "objective_stated": bool(objective),
                             "instrument_version": pool.version_tag or (("2026-09-30-contest-c" if pool.spec_revisions else
                                                     "2026-09-30-contest-b" if pool.filing_status else "2026-09-29-contest")
                                                    if pool.contest else
                                                    ("2026-09-27-program" if pool.program_target or pool.unreviewed else
                                                     ("2026-09-26-coded-c" if pool.records.report_back else "2026-09-26-coded-b")
                                                     if pool.records.own_panels else "2026-09-26-coded")
                                                    if pool.pres.enabled else "2026-09-26-exact"),
                             "institution": pool.institution or None,
                             "allocation": pool.allocation if pool.institution == "competitive" else None,
                             "success_floor": pool.success_floor if pool.allocation == "divisible" else None,
                             "success_cap": pool.success_cap if pool.allocation == "divisible" else None,
                             "credit_threshold": pool.credit_threshold if pool.institution == "cooperative" else None,
                             "program_target": pool.program_target or None, "unreviewed": pool.unreviewed,
                             "feasible_count_stated": bool(pool.feasible_text),
                             "refinement": pool.inst.refinement or None, "contest": pool.contest,
                             "report_back": pool.records.report_back, "filing_status": pool.filing_status,
                             "spec_revisions": [{"minute": r["minute"], "steps": float(r["steps"]), "label": r["label"]}
                                                for r in pool.spec_revisions] or None,
                             "program_lines": pool.program_lines, "deadline_review": pool.deadline_review,
                             "rule_level": pool.rule_level or None, "concern_board": pool.concern_board or None,
                             "board": pool.board_settings or None,
                             "concern_effect_stated": pool.concern_effect_stated if pool.concern_board else None,
                             "strict_report": pool.records.strict_report,
                             "restricted": ({"component": pool.inst.restricted[0], "setting": pool.inst.restricted[1],
                                             "gain": pool.inst.restricted_gain, "note": pool.restricted_note,
                                             "legacy": {pid: list(r) for pid, r in pool.legacy.items()} or None,
                                             "shown_as": pool.variant_text()}
                                            if pool.inst.restricted is not None else None),
                             "seeded_projects": list(pool.seeded_projects),
                             # supplier-k: the runtime's texts reached the agents reworded (vocabulary.py); the
                             # texts events record are the laboratory wording unless the event says otherwise.
                             **({"vocabulary": pool.vocabulary} if pool.vocabulary else {}),
                             "audit_probability": pool.audit_probability, "peer_review": pool.peer_review,
                             "guidance_stated": bool(pool.guidance_text)})
                await _deliver(MailboxItem(item_id=new_ulid(), kind="note",
                                           payload=start_note_text(pool, tc.agent_id, objective)),
                               tc.agent_id, ctx.rs)
            if pool.deliberation_text:  # the open topic is post #1, before any lab acts
                await open_topic(self._ensure_board(pool), ctx.rs, pool.speaker, pool.say(pool.deliberation_text), ctx.spine)
            await pool.run()

        return orchestrate
