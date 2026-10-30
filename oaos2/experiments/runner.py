"""Execute a task under an organization and preserve its results and evidence.

run_one provides simulated execution; run_org_live uses model adapters and a
container backend; run_sweep expands a loaded design into repeated conditions.
Tasks and organization presets come from library/ through validated loaders.
Task scorers and coordination procedures are selected through registered plugins.

Each run records its resolved inputs, manages agents and declared work dependencies,
accepts commitments, evaluates outcomes, records failures, and closes its archive.
Clocked tasks additionally schedule notices and deadlines. Live resource cleanup
is managed by RunSession. See docs/SYSTEM.md for the component map and
experiments/confirmatory.py for pre-run research checks."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from oaos2.evaluation.public_feedback import write_evaluation
from oaos2.organizations.spec import OrganizationSpec
from oaos2.kernel.manifest import Manifest
from oaos2.kernel.run_dir import RunDir
from oaos2.kernel.runtime import ActionPlan, build_runtime, make_agent, run_supervisor
from oaos2.outcomes.commit import OutcomeCoordinator
from oaos2.outcomes.conformance import CommitmentConformanceError
from oaos2.outcomes.label import label_outcome
from oaos2.pricing.table import foundation_pricing_table
from oaos2.tasks.pack import TaskPack
from oaos2.tasks.loader import load_task_pack
from oaos2.trace.retention import RetentionPolicy, RunMode
from oaos2.trace.spine import RunSpine


def _nested_exception(exc: BaseException, kind: type[BaseException]):
    """Return the first ``kind`` nested in a TaskGroup exception, if present."""
    if isinstance(exc, kind):
        return exc
    for child in getattr(exc, "exceptions", ()):
        found = _nested_exception(child, kind)
        if found is not None:
            return found
    return None


def _packet_scope(role):
    """The environment scope(s) a role receives packets for: its attention scope,
    widened by any declared ``packet_scopes`` (CH1 evidence arm). A str when
    nothing is declared, so every existing consumer/test sees today's value."""
    extra = tuple(getattr(role, "packet_scopes", ()) or ())
    return (role.attention, *extra) if extra else role.attention


@dataclass
class CellResult:
    preset_id: str
    model_ref: str
    closed: bool
    passed: bool
    label: str  # assisted | unassisted
    archive_valid: bool
    scored: bool = True  # headline evaluation completed; distinct from outcome closure
    score_detail: dict = field(default_factory=dict)
    n_agents: int = 0
    run_dir: Path | None = None
    partial_score: float | None = None
    cost_usd: float | None = None
    output_tokens: int | None = None
    difficulty: str | None = None
    context_budget: int | None = None  # per-agent context cap this cell ran under (IV; None = unbounded)
    # Clocked cells: the horizon this cell ran under (the load-to-capacity IV;
    # None = batched), and the canonical clock-factor label (e.g. "r24w7" —
    # horizon AND burstiness; audit round 5 P1-1: two burstiness variants at
    # one horizon must never aggregate as one condition). The label keys every
    # downstream grouping (confound gate, headline, parity, run_status).
    rounds_total: int | None = None
    clock_label: str | None = None
    # Parity invariants pinned per cell — confound_check asserts these are identical
    # across compared cells (DESIGN §15, §10.2, M7 §4). usd-basis parity is only
    # meaningful if the price table AND the cache-breakpoint policy match; a differing
    # exposure is a confound that confirmatory refuses (M3 §2.1).
    pricing_table_version: str | None = None
    pricing_table_hash: str | None = None
    cache_policy_fingerprint: str | None = None  # None for offline cells (no model calls)
    exposure_confounded: bool = False
    # Loop provenance for the confirmatory runtime gate (DESIGN §10.1/§24): only the
    # host-owned raw_api loop is permitted in confirmatory cells. Every construction
    # path stamps this explicitly ("raw_api" live, "offline_stub" for run_one) so
    # confound_check's gate is mechanical, not author discipline; the None default is
    # fail-closed — an unstamped cell is barred from a confirmatory comparison.
    runtime: str | None = None
    declared_treatments: list = field(default_factory=list)  # treatment ids this cell legitimately defines
    # Which ParityPolicy regime this cell ran under (M7 §4). None = no parity claim
    # (a lone run_org_live cell); run_sweep stamps the regime it dispatched.
    parity_regime: str | None = None
    parity_basis: str = "usd"
    # Per-role EFFECTIVE model binding {role_id: model_ref} (C1h): `role.model_ref or
    # <run model_ref>`, stamped on every construction path (homogeneous runs included)
    # — the confound gate compares it within a preset; `model_ref` above stays the
    # run-level ref roles inherit.
    role_model_refs: dict = field(default_factory=dict)


def _role_model_refs(org_spec: OrganizationSpec, model_ref: str) -> dict:
    """The per-role EFFECTIVE binding, sorted by role_id (it is a manifest/run_status
    pin, so its rendering must be stable): a role's own ``model_ref`` wins, else the
    run-level factor. The one place the rule lives."""
    return {r.role_id: (r.model_ref or model_ref)
            for r in sorted(org_spec.roles, key=lambda r: r.role_id)}


def _takes_effort(model_ref: str) -> bool:
    """True iff the model's reasoning is set by an effort level, not a token budget."""
    from oaos2.models.adapters.anthropic import EFFORT_MODELS
    provider, _, model = model_ref.partition("/")
    return provider == "anthropic" and model in EFFORT_MODELS


def _role_reasoning(role_model_refs: dict, *, reasoning_kind: str,
                    reasoning_budget: int | None, effort: str | None) -> dict:
    """The reasoning settings each role's model is actually sent, by role_id.

    A budget model gets the run's budget; ``effort`` does not apply to it. An effort
    model gets the run's effort and no budget, since it refuses one, and the provider's
    default sampling (the adapter sends no temperature). The archived neutral requests
    still show the platform's temperatures, so this record is the authority. Refuses,
    before anything is staged, an effort model without an effort level, and effort
    xhigh or max on one: the recap and discussion calls ask for no reasoning, which
    the provider allows only at effort high or below."""
    from oaos2.models.adapters.anthropic import EFFORT_LEVELS
    if effort is not None and effort not in EFFORT_LEVELS:
        raise ValueError(f"effort must be one of {EFFORT_LEVELS}, not {effort!r}")
    out = {}
    for role_id, ref in role_model_refs.items():
        if not _takes_effort(ref):
            out[role_id] = {"reasoning_budget": reasoning_budget if reasoning_kind != "none" else None}
            continue
        if effort is None:
            raise ValueError(f"role {role_id!r} runs {ref}, which takes an effort level, not a "
                             "reasoning budget; set effort explicitly (a study setting)")
        if effort in ("xhigh", "max"):
            raise ValueError(f"role {role_id!r} runs {ref} at effort {effort!r}: its recap and "
                             "discussion calls ask for no reasoning, which the provider allows only "
                             "at effort high or below. Decide how those calls reason before using it.")
        out[role_id] = {"effort": effort, "reasoning_budget": None, "sampling": "provider_default"}
    return dict(sorted(out.items()))


def _pricing_table_for(model_refs):
    """The oldest table that prices every bound model. Studies keep one pricing identity
    across cells, which the confound check requires, so a table is never edited and a
    model is priced by the first table that has it.

    The order joins two lineages (consolidation, October 19, 2026). T1's: the foundation
    table, 2026-10-03 (Claude Sonnet 5.5), 2026-10-10 (Claude Haiku 5.5), 2026-10-19
    (GPT-5-mini and two OpenRouter models, built on 2026-10-10). PC1's, after 2026-10-10:
    2026-10-12, -13, -15 and -16 (its other providers). T1's runs price exactly as on T1.
    PC1's differ only where its chain skipped 2026-10-03 or a model is also in 2026-10-19:
    Claude Sonnet 5.5 is priced on 2026-10-03 (cache reads overstated, as that table
    records), and a run on GPT-5-mini or Qwen 3.8 Flash alone on 2026-10-19 (GPT-5-mini at
    the same rates; Qwen with a cached-input rate 2026-10-15 lacks). PC1's main-study
    models (GLM-5.3-Flash through OpenRouter, gpt-6-luna, Claude Sonnet 4.6) are unaffected."""
    from oaos2.pricing.table import (pricing_table_2026_10_03, pricing_table_2026_10_10, pricing_table_2026_10_12,
                                     pricing_table_2026_10_13, pricing_table_2026_10_15, pricing_table_2026_10_16,
                                     pricing_table_2026_10_19)
    refs = [ref for ref in model_refs if not ref.startswith("stub/")]
    for make in (foundation_pricing_table, pricing_table_2026_10_03, pricing_table_2026_10_10,
                 pricing_table_2026_10_19, pricing_table_2026_10_12, pricing_table_2026_10_13,
                 pricing_table_2026_10_15):
        table = make()
        if all(ref in table.rows for ref in refs):
            return table
    return pricing_table_2026_10_16()  # October 16: gpt-5.6-terra


def _launch_model_refs(model_refs, org_specs) -> tuple:
    """Every model snapshot a launch will actually dispatch: the run-level refs UNION
    every preset's role-level overrides — readiness must demand capacity evidence for
    each of them (M7 §8 Q2), not only the inherited factor."""
    refs = set(model_refs)
    for o in org_specs:
        refs.update(r.model_ref for r in o.roles if r.model_ref)
    return tuple(sorted(refs))


def _adapter_from_factory(factory, model_ref: str):
    """Test seam: ``adapter_factory`` overrides the registry for every role; a factory
    that declares a ``model_ref`` kwarg receives the role's effective ref so a test can
    bind distinct stubs per role. A bare factory is called exactly as before."""
    try:
        params = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return factory()
    if "model_ref" in params or any(p.kind is inspect.Parameter.VAR_KEYWORD
                                    for p in params.values()):
        return factory(model_ref=model_ref)
    return factory()


def _role_model_facts(events: list) -> dict:
    """Per-role realized cost/tokens from the spine (one pass; the shared ``CostLedger``
    stays the single ceiling — this is an OUTCOME partition of the same ``cost.recorded``
    records, never a parity basis). Roles that never invoked are absent. Sorted keys:
    run_status is a pin."""
    cost: dict = {}
    tokens: dict = {}
    for e in events:
        agent, p = e.get("agent_id"), (e.get("payload") or {})
        if not agent or e.get("event_class") != "cost.recorded":
            continue
        cost[agent] = cost.get(agent, 0.0) + float(p.get("cost_usd") or 0.0)
        tokens[agent] = tokens.get(agent, 0) + int((p.get("token_split") or {}).get("output") or 0)
    return {"cost_by_role": {a: round(v, 6) for a, v in sorted(cost.items())},
            "output_tokens_by_role": dict(sorted(tokens.items()))}


def _realized_reasoning_kind(adapter, reasoning_kind: str, model_ref: str | None = None) -> str | None:
    """How THIS role's provider realizes the neutral reasoning request (C1h, mixed
    orgs): the model-specific capability when declared, otherwise the adapter's
    provider-level surface; "none" when no reasoning was requested. Some adapters
    echo the requested kind on their responses, so those alone cannot establish
    whether the returned reasoning is a summary."""
    if reasoning_kind == "none":
        return "none"
    model_caps = getattr(adapter, "capabilities_for", None)
    caps = (model_caps(model_ref) if model_caps is not None and model_ref is not None
            else getattr(adapter, "capabilities", None))
    return getattr(caps, "reasoning_kind", None)


def _milestones_for_roles(contract, plays: set[str]) -> list[str]:
    """Milestones this agent may commit = those whose committer_roles intersect the
    roles it plays (§13). The org never names milestone ids; the TASK binds them."""
    return [c.commitment_id for c in contract.commitments
            if not c.committer_roles or set(c.committer_roles) & plays]


def _headline_ref_sha(pack: TaskPack, tier: str | None = None) -> str | None:
    """Return the first headline evaluator's hidden-reference hash, or None.

    Pass the cell's tier when the evaluator accepts it, so the manifest identifies
    the scoring reference actually selected."""
    for ev in pack.evaluators.values():
        if getattr(ev, "produces_headline_score", False) and hasattr(ev, "input_ref"):
            params = inspect.signature(ev.input_ref).parameters
            ref = ev.input_ref(tier=tier) if "tier" in params else ev.input_ref()
            return ref.content_hash if ref else None
    return None


def _sha256_file(path: Path | str | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def _sha256_json(value) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _write_resolved_sweep(rd: RunDir, plan: dict | None) -> str | None:
    """Persist the actual post-CLI sweep plan inside every cell archive.

    The source YAML hash is necessary but insufficient because launchers may narrow
    factors or override reps/caps in memory. This byte hash enters ``apparatus_sha256``.
    """
    if plan is None:
        return None
    path = rd.config / "resolved_sweep.json"
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    return _sha256_file(path)


@lru_cache(maxsize=1)
def _source_state() -> dict:
    """Best-effort code identity, commit, and dirty-worktree fingerprint.

    A commit hash alone is not reproducible when a live run is launched from local
    modifications. Hash the tracked diff and every untracked file without storing their
    contents in the archive. The separate source-code hash excludes documents and
    launch pins, so committing those pins does not invalidate their own identity.
    Source tarballs legitimately return unknown Git values.
    """
    code_sha = None
    try:
        from oaos2.experiments.source_identity import source_code_sha256
        root = Path(__file__).resolve().parents[2]
        code_sha = source_code_sha256(root)
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
            capture_output=True, text=True, timeout=2).stdout.strip() or None
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z"], check=True,
            capture_output=True, timeout=3).stdout
        dirty = bool(status)
        worktree_sha = None
        if dirty:
            digest = hashlib.sha256()
            digest.update(subprocess.run(
                ["git", "-C", str(root), "diff", "--binary", "HEAD", "--"], check=True,
                capture_output=True, timeout=5).stdout)
            untracked = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"],
                check=True, capture_output=True, timeout=3).stdout.split(b"\0")
            for raw in sorted(p for p in untracked if p):
                path = root / raw.decode(errors="surrogateescape")
                digest.update(raw + b"\0")
                if path.is_file():
                    digest.update(path.read_bytes())
            worktree_sha = "sha256:" + digest.hexdigest()
        return {"source_commit": commit, "source_dirty": dirty,
                "source_worktree_sha256": worktree_sha, "source_code_sha256": code_sha}
    except Exception:  # noqa: BLE001 — source tarballs legitimately have no .git
        return {"source_commit": None, "source_dirty": None,
                "source_worktree_sha256": None, "source_code_sha256": code_sha}


def _apparatus_pins(pack: TaskPack, org_spec: OrganizationSpec, *, tier: str | None,
                    preregistration_ref: str | None = None,
                    design_ref: Path | str | None = None,
                    resolved_sweep_sha256: str | None = None) -> dict:
    """Hash every claim-bearing apparatus input available before execution."""
    from oaos2.library import library_dir

    repo = library_dir().parent
    prereg = Path(preregistration_ref) if preregistration_ref else None
    if prereg is not None and not prereg.is_absolute():
        prereg = repo / prereg
    visible = {}
    if tier in pack.tier_materials and pack.visible_dir is not None:
        visible = {name: _sha256_file(pack.visible_dir / name)
                   for name in sorted(pack.tier_materials[tier])}
    prompts = {role: _sha256_json(packet.instructions)
               for role, packet in sorted(pack.role_packets.items())}
    evaluator_sources = {}
    for ref, evaluator in sorted(pack.evaluators.items()):
        source = inspect.getsourcefile(type(evaluator))
        evaluator_sources[ref] = _sha256_file(source)
    pins = {
        **_source_state(),
        "design_ref": str(design_ref) if design_ref else None,
        "design_sha256": _sha256_file(design_ref),
        "resolved_sweep_sha256": resolved_sweep_sha256,
        "organization_ref": str(org_spec.source_ref) if org_spec.source_ref else None,
        "organization_sha256": _sha256_file(org_spec.source_ref),
        # an overlay preset's bases, outermost first; recorded only when the preset names a base
        **({"organization_bases": [{"ref": str(b), "sha256": _sha256_file(b)} for b in org_spec.base_refs]}
           if getattr(org_spec, "base_refs", ()) else {}),
        "task_manifest_ref": str(pack.manifest_path) if pack.manifest_path else None,
        "task_manifest_sha256": _sha256_file(pack.manifest_path),
        "contract_profile": pack.contract_profile,
        "preregistration_sha256": _sha256_file(prereg),
        "hidden_reference_sha256s": {
            ref: spec.get("sha256") for ref, spec in sorted(pack.hidden_refs.items())
        },
        "environment_driver": pack.environment.get("driver") if pack.environment else None,
        # The schedule THIS cell dispatches from — the variant's hash when the
        # resolved ClockSpec selects one (audit round 5 P1-2: variant cells
        # previously fingerprinted the canonical schedule, so r24 and r36
        # archives carried the identical apparatus identity).
        "environment_schedule_sha256": (_resolved_schedule_pin(pack, tier)
                                        if pack.environment else None),
        "environment_schedule_variant": (
            pack.clock.schedule_variant
            if pack.clock is not None
            and pack.clock.is_clocked_profile(pack.contract_profile) else None),
        # The resolved (post-override) clock enters the fingerprint: two cells
        # differing only in horizon/deadlines/megabatch are different apparatus.
        "clock_spec": (pack.clock.to_manifest()
                       if pack.clock is not None
                       and pack.clock.is_clocked_profile(pack.contract_profile)
                       else None),
        "visible_material_sha256s": visible,
        "role_prompt_sha256s": prompts,
        "evaluator_source_sha256s": evaluator_sources,
    }
    pins["apparatus_sha256"] = _sha256_json(pins)
    return pins


def _research_setup_sha(pack, org_spec, *, tier, model_ref, context_budget,
                        cap_usd, cap_output_tokens, final_reserve_tokens, parity_basis,
                        reasoning_kind="thinking", reasoning_budget=8000,
                        interleaved_thinking=True, max_model_calls=200,
                        wall_clock_cap=180, image_ref="oaos2-science:py311",
                        integrator_role=None, effort=None):
    """Fingerprint the actual research inputs, excluding names of batches and files."""
    from dataclasses import asdict
    pins = _apparatus_pins(pack, org_spec, tier=tier)
    selected = {k: pins[k] for k in (
        "task_manifest_sha256", "contract_profile", "hidden_reference_sha256s",
        "environment_driver", "environment_schedule_sha256", "clock_spec",
        "visible_material_sha256s", "role_prompt_sha256s", "evaluator_source_sha256s")}
    selected["source_code_sha256"] = pins.get("source_code_sha256")
    data_source = pack.data_mount_source()
    selected["data_mount_sha256s"] = {
        str(p.relative_to(data_source)): _sha256_file(p)
        for p in sorted(data_source.rglob("*")) if p.is_file()}
    from oaos2.agents.model_agent import DEFAULT_CACHE_POLICY, DELIBERATION_CACHE_POLICY
    # Only when a role's model takes it: every other setup keeps its fingerprint.
    if any(_takes_effort(r) for r in _role_model_refs(org_spec, model_ref).values()):
        selected["effort"] = effort
    selected.update(
        reasoning_kind=reasoning_kind, reasoning_budget=reasoning_budget,
        interleaved_thinking=interleaved_thinking, max_model_calls=max_model_calls,
        wall_clock_cap=wall_clock_cap, image_ref=image_ref, integrator_role=integrator_role,
        cache_policy=[DEFAULT_CACHE_POLICY.fingerprint(), DELIBERATION_CACHE_POLICY.fingerprint()],
        pricing_table_hash=_pricing_table_for(_role_model_refs(org_spec, model_ref).values()).hash(),
        precedence_rules=org_spec.precedence_rules, context_expansion=org_spec.context_expansion,
        schema_version=1, task_pack=pack.pack_id, tier=tier, model_ref=model_ref,
        roles=[asdict(r) for r in org_spec.roles],
        scheduler=org_spec.scheduler, committer_binding=org_spec.committer_binding,
        tools=sorted(org_spec.tools) if org_spec.tools is not None else None,
        topology=asdict(org_spec.topology) if org_spec.topology is not None else None,
        coordination=org_spec.live_coordination, context_budget=context_budget,
        cap_usd=cap_usd, cap_output_tokens=cap_output_tokens,
        final_reserve_tokens=final_reserve_tokens if cap_output_tokens is not None else 0,
        parity_basis=parity_basis)
    # Role tool/kind grants may be sets; sort them before JSON encoding.
    def canonical(value):
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in sorted(value.items())}
        if isinstance(value, (set, frozenset)):
            return sorted(canonical(v) for v in value)
        if isinstance(value, (list, tuple)):
            return [canonical(v) for v in value]
        return value
    return _sha256_json(canonical(selected))


def _resolved_schedule_pin(pack: TaskPack, tier: str | None) -> str | None:
    """content_hash of the schedule this cell actually dispatches from
    (variant-aware; mirrors build_environment_driver's selection)."""
    variant = (pack.clock.schedule_variant
               if pack.clock is not None
               and pack.clock.is_clocked_profile(pack.contract_profile) else None)
    if variant is not None:
        sched = pack.environment.get("schedule_variants", {}).get(variant, {}).get(tier)
    else:
        sched = pack.environment.get("schedules", {}).get(tier)
    return (sched or {}).get("content_hash")


def _solver_for(pack):
    """Find the simulated solver used for an offline task check.

    Prefer the manifest's offline_solver, then the conventional task-plugin
    module. Import failures in a supplied solver are errors. Use the generic
    structural stub only when the task supplies no solver."""
    import importlib
    import importlib.util
    declared = getattr(pack, "offline_solver", None)
    if declared:
        try:
            return importlib.import_module(str(declared)).produce_milestone_payload
        except Exception as exc:  # noqa: BLE001 — a declared solver is fail-closed
            raise RuntimeError(
                f"pack {pack.pack_id!r}: declared offline_solver {declared!r} "
                f"failed to import: {exc}") from exc
    mod_name = f"oaos2.tasks.plugins.{pack.pack_id}.solver"
    try:
        found = importlib.util.find_spec(mod_name)
        pkg_exists = True
    except ModuleNotFoundError:
        found, pkg_exists = None, False  # the pack's plugin package itself does not exist
    if found is not None:
        return importlib.import_module(mod_name).produce_milestone_payload
    if pkg_exists:
        # Probe round 2 (latent): a pack that SHIPS a plugin package but no
        # solver submodule is a mis-named/missing solver, not a solver-less
        # pack — silently substituting another domain's solver would mask it.
        raise RuntimeError(
            f"pack {pack.pack_id!r} ships a plugin package but no `solver` "
            "module — add plugins/<pack_id>/solver.py or declare "
            "`offline_solver:` in the manifest")
    from oaos2.tasks.plugins.paper_replication.solver import produce_milestone_payload
    return produce_milestone_payload


def _make_solver(coordinator: OutcomeCoordinator, plays: set[str], specialized: bool, session_id: str,
                 solver_fn, *, tier: str | None = None):
    owns = _milestones_for_roles(coordinator.contract, plays)

    async def behave(agent, rs, ctx) -> ActionPlan:
        for m in owns:
            if m == "review_v1":
                continue  # optional + Tier-C rubric deferred (M7 §2.4)
            if m in coordinator.committed:
                continue
            c = coordinator.contract.commitment(m)
            if not all(b in coordinator.committed for b in c.blocks):
                return ActionPlan(result="finish_turn")  # wait for blocker (data dependency)
            tier_kw = ({"tier": tier} if "tier" in inspect.signature(solver_fn).parameters else {})
            payload = solver_fn(m, specialized, **tier_kw)
            await coordinator.commit(
                commitment_id=m, payload=payload, agent_id=agent.agent_id,
                session_id=session_id, caused_by=ctx.caused_by,
            )
            return ActionPlan(result="finish_turn")  # committed one; loop for more
        return ActionPlan(result="retire")

    return behave


async def run_one(
    pack: TaskPack,
    org_spec: OrganizationSpec,
    runs_root: Path,
    *,
    run_id: str,
    experiment_id: str = "exp1",
    mode: str = "pilot",
    model_ref: str = "stub/deterministic",
    tier: str | None = None,
    preregistration_ref: str | None = None,
    design_ref: Path | str | None = None,
    resolved_sweep_plan: dict | None = None,
) -> CellResult:
    org_spec.validate()  # structure load-time gate offline too (not only on the live path)
    role_model_refs = _role_model_refs(org_spec, model_ref)  # stub solver: stamped, not bound
    rd = RunDir.create(runs_root, experiment_id, pack.pack_id, run_id)
    table = foundation_pricing_table()
    retention = RetentionPolicy()
    retention.validate_for_mode(RunMode(mode))
    resolved_sweep_sha = _write_resolved_sweep(rd, resolved_sweep_plan)
    manifest = Manifest(
        run_id=run_id, experiment_id=experiment_id, task_pack_id=pack.pack_id, mode=mode,
        pricing_table_version=table.version, organization_id=org_spec.preset_id,
        retention_policy_hash=_sha256_json(retention.model_dump()),
    )
    manifest.extensions.update({
        "pricing_table_hash": table.hash(),
        "reference_sha256": _headline_ref_sha(pack, tier),
        "difficulty": tier,
        "role_model_refs": role_model_refs,  # stamped on EVERY run (offline included)
        "model_heterogeneous": len(set(role_model_refs.values())) > 1,
        "resolved_sweep_ref": ("config/resolved_sweep.json"
                               if resolved_sweep_sha is not None else None),
        "missing_optional_refs": list(pack.missing_optional_refs),  # scoring-degradation audit (M7 §2.2)
        "retention_policy": retention.model_dump(),
        **_apparatus_pins(pack, org_spec, tier=tier,
                          preregistration_ref=preregistration_ref, design_ref=design_ref,
                          resolved_sweep_sha256=resolved_sweep_sha),
    })
    manifest.write(rd.manifest_path)

    # run_one shares the SAME lifecycle object as the live path (audit round 8
    # P1-3): once the spine starts, every failure — supervisor, scoring,
    # labeling, rendering — aborts through the session and writes a terminal
    # record. Offline is not exempt from the archive-trustworthiness invariant.
    from oaos2.experiments.session import RunSession
    session = RunSession(rd, run_id)
    session.preflight_ok()
    spine = _pack_spine(rd, run_id, pack)
    await spine.start()
    session.attach_resources(spine=spine, backend=None, policy=None)

    contract = copy.deepcopy(pack.outcome_contract)
    coordinator = OutcomeCoordinator(contract, spine, rd.submitted)

    all_roles = {r for c in contract.commitments for r in c.committer_roles}
    solver_fn = _solver_for(pack)  # manifest-declared, else convention (fail-closed on broken imports)
    agents = []
    for role in org_spec.roles:
        # committer_binding="any" → the agent plays every role (can commit anything);
        # otherwise it plays the roles declared on the org Role.
        plays = all_roles if org_spec.committer_binding == "any" else set(role.plays)
        behave = _make_solver(coordinator, plays, role.specialized, session_id=f"s_{role.role_id}",
                              solver_fn=solver_fn, tier=tier)
        agents.append(make_agent(role.role_id, behave, role_id=role.role_id))

    rs = build_runtime(spine, agents, scheduler=org_spec.scheduler,
                       router=_pack_router(pack))
    rs.environment_scopes = {r.role_id: _packet_scope(r) for r in org_spec.roles}
    coordinator.on_close = rs.close_outcome
    from oaos2.environment import build_environment_driver, dispatch_after_commit
    environment_driver = build_environment_driver(pack.environment, tier)
    if environment_driver is not None:
        async def _dispatch_environment(commitment_id, _state_commitment, committed_event):
            await dispatch_after_commit(
                environment_driver, commitment_id=commitment_id,
                runtime_state=rs, caused_by=committed_event,
            )
        coordinator.on_commit = _dispatch_environment
    # Deadlock backstop, scaled to contract size: the flat 15s calibrated on small
    # contracts starved budget_execution's 45-commitment DAG mid-wave (real completion
    # ~22s offline). ~2s/commitment keeps the bound tight enough to catch a true stall.
    session.begin_execution()
    try:
        await asyncio.wait_for(run_supervisor(rs),
                               timeout=max(15, 2 * len(contract.commitments)))
        session.begin_winddown()

        if environment_driver is not None:
            environment_driver.assert_complete()

        score = await _score(pack, coordinator, spine, tier=tier)
        if mode == "confirmatory" and not score["scored"]:
            await session.finalize("failed")
            _render_derived(rd.root)
            raise RuntimeError("confirmatory cell closed without a successful headline evaluation")
        label = label_outcome(rd.root, list(coordinator.committed_event_ids.values()))
        report = await session.finalize("completed")
        # HARD-ERROR CONTRACT (DESIGN §6.3, probe 2026-08-17): a non-ok invariant
        # report is a failed run, never an ordinary CellResult with a false flag —
        # raise RunFailed so the sweep's failure capture records the cell as failed.
        spine.raise_if_invalid()
        _render_derived(rd.root)  # re-render derived/ transcripts + metrics from the frozen archive
    except BaseException as _exc:  # noqa: BLE001 — abort re-raises
        await session.abort(_exc)

    partial = score.get("partial_score")  # headline evaluator's score (None if it has none)
    result = CellResult(
        preset_id=org_spec.preset_id, model_ref=model_ref, closed=coordinator.closed,
        passed=score["passed"], label=label, archive_valid=report.ok, scored=score["scored"],
        score_detail=score, n_agents=org_spec.n_agents, run_dir=rd.root,
        partial_score=partial, cost_usd=0.0, difficulty=tier,
        pricing_table_version=table.version, pricing_table_hash=table.hash(),
        cache_policy_fingerprint=None,  # offline: stub solver, no model calls → no cache policy
        exposure_confounded=False,
        runtime="offline_stub",  # NOT raw_api: a stub cell can never enter a confirmatory comparison
        rounds_total=None, clock_label=None,  # run_one is the batched offline path — never clocked
        role_model_refs=role_model_refs,
    )
    _persist_run_status(rd.root, result)
    return result


async def run_paper_replication_live(
    runs_root: Path,
    *,
    tier: str,
    run_id: str | None = None,
    model_ref: str = "anthropic/claude-sonnet-4-6",
    experiment_id: str = "exp_live",
    cap_usd: float = 3.0,
    # Extended thinking ON by default — captures the agent's chain-of-thought
    # (the old platform's enable_extended_thinking). The adapter records the thinking
    # blocks verbatim in raw/ and surfaces the text in reasoning.step.payload.thinking.
    reasoning_kind: str = "thinking",
    reasoning_budget: int | None = 8000,
    effort: str | None = None,  # effort-level models only (see run_org_live)
    wall_clock_cap: int = 180,
    image_ref: str = "oaos2-science:py311",
    max_model_calls: int = 200,  # high ceiling; COST is the primary stopper (old-platform model)
) -> CellResult:
    """A real single-agent paper-replication run — a thin wrapper over ``run_org_live``
    with the ``single_agent`` preset, so the single live code path is shared (no drift).
    Kept for API stability; ``run_org_live(single_agent(), ...)`` is equivalent.
    """
    from oaos2.organizations.presets import single_agent

    return await run_org_live(
        single_agent(), runs_root, tier=tier, run_id=run_id, model_ref=model_ref,
        experiment_id=experiment_id, cap_usd=cap_usd, reasoning_kind=reasoning_kind,
        reasoning_budget=reasoning_budget, effort=effort, wall_clock_cap=wall_clock_cap,
        image_ref=image_ref, max_model_calls=max_model_calls,
    )


# --------------------------------------------------------------------------- #
# Multi-agent live coordination — all four confirmatory arms (M7 §3, §5)
# --------------------------------------------------------------------------- #
# Which role packet seeds each agent's prompt is DECLARED on the org Role
# (``role_packet``, config-over-code), defaulting to the role_id — the runner never
# hardcodes a preset→packet table. The decomposed-role + control packets are
# UNCALIBRATED DRAFTS (M7 §8 Q2).


def _resolve_org(preset_id: str):
    """A sweep arm is any org preset: a built-in builder if registered, else a library YAML
    loaded by name (config-as-data — a new org structure is just a YAML, e.g. budget_organic)."""
    from oaos2.organizations.loader import load_org_spec
    from oaos2.organizations.presets import ALL_PRESETS
    return ALL_PRESETS[preset_id]() if preset_id in ALL_PRESETS else load_org_spec(preset_id)


def _build_ceiling_fallback(spec: dict, coordinator, commitment) -> dict:
    """Materialize a contract-declared per-slot capacity fallback (data-driven, task-neutral).

    ``spec`` keys: ``static`` (literal payload base), ``carry_forward`` (field names copied
    from the most recent committed payload carrying them), ``cover_dispositions``
    ({disposition, reason} applied to every record the slot's own
    ``record_dispositions_cover`` gate owes).  The result must clear the slot's normal
    conformance gate — commit() remains the final authority; a nonconformant fallback is
    refused loudly, never smuggled."""
    payload = dict(spec.get("static") or {})
    for field_name in spec.get("carry_forward") or []:
        for cid in reversed(list(coordinator.payloads)):
            source = coordinator.payloads[cid]
            if isinstance(source, dict) and field_name in source:
                payload[field_name] = source[field_name]
                break
    cover = spec.get("cover_dispositions")
    if cover:
        rdc = (commitment.submission or {}).get("record_dispositions_cover") or {}
        prefix = str(rdc.get("source_prefix", ""))
        records_field = rdc.get("records_field", "exception_records")
        id_field = rdc.get("id_field", "exception_id")
        owed: set[str] = set()
        for cid in sorted(coordinator.payloads):
            if not cid.startswith(prefix):
                continue
            source = coordinator.payloads[cid]
            records = source.get(records_field) if isinstance(source, dict) else None
            for record in records if isinstance(records, list) else []:
                if isinstance(record, dict):
                    rid = str(record.get(id_field, "")).strip()
                    if rid:
                        owed.add(rid)
        payload[rdc.get("field", "exception_dispositions")] = {
            rid: {"disposition": cover.get("disposition", "referred"),
                  "reason": cover.get("reason", "capacity ceiling reached")}
            for rid in sorted(owed)}
    return payload


def _commitment_duty(contract, commitment_id: str, *,
                     continuous: bool = False) -> str:
    """Participant-visible, task-neutral description of the currently bound slot.

    ``continuous`` (clocked runs): the tail invites finishing several duties in
    one working day instead of the batched-era "work only on this slot" framing,
    which — together with the old "Task complete." confirmation — had closed the
    megabatch escape valve entirely (density calibration, 2026-08-15)."""
    commitment = contract.commitment(commitment_id)
    required = list((commitment.submission or {}).get("required", []))
    fields = (" Required top-level JSON fields: " + ", ".join(required) + "."
              if required else "")
    # Optional contract-declared teaching line (config-as-data): the clocked
    # per-case slots carry shapes the fund brief does not teach, so the duty
    # notice itself states them (apparatus text, arm-identical).
    note = str((commitment.submission or {}).get("duty_note") or "").strip()
    note = f" {note}" if note else ""
    from oaos2.outcomes.conformance import duty_cap_note
    note += duty_cap_note(commitment.submission)  # states the free-text cap only where the slot sets one
    tail = (
        " Call `submit_results` when it is ready; when it commits, your next "
        "duty is handed to you at once, and you may keep working within the "
        "same day or stop and resume the next day."
        if continuous else
        " Work only on this slot and call `submit_results` when it is ready; "
        "the platform will announce any later slot.")
    return (
        f"# Current commitment\nYour currently authorized submission is "
        f"`{commitment_id}`.{fields}{note}{tail}\n"
    )


def _update_rounds(driver) -> dict:
    """Later notices on scheduled cases (context-shift schedules); {} for a driver or a
    schedule that has none."""
    fn = getattr(driver, "update_rounds", None)
    return dict(fn()) if callable(fn) else {}


def _case_file_text(rs, commitment_id: str, agent_id: str) -> str:
    """The case file a duty notice carries for its slot (outcomes/case_file.py); '' when
    the slot declares none or the run set no builder (batched runs)."""
    builder = getattr(rs, "case_file_builder", None) if rs is not None else None
    if builder is None:
        return ""
    text = builder(commitment_id, agent_id)
    return f"\n{text}" if text else ""


def _role_file_policy(role):
    """Per-role file-access ACL from the role's tool grant (DESIGN §18.1, §9, §8).

    A role may READ the mounted zones; it may WRITE/EXECUTE its own scratch ONLY if it
    holds a write/execute tool. So a read-only role (reader/reviewer) is denied at the ACL
    layer too, not merely un-offered the tool — OS/dispatch-enforced, not author discipline.
    """
    from oaos2.workspace.acl import FileAccessPolicy
    scratch = f"scratch_{role.role_id}"
    tools = set(role.tools) if role.tools is not None else {"run_python", "read_file", "write_file", "submit_results"}
    can_write = bool({"write_file", "run_python"} & tools)
    can_exec = "run_python" in tools
    return FileAccessPolicy(
        zones_visible=frozenset({"visible", scratch, "shared", "submitted"}),
        zones_writable=frozenset({scratch}) if can_write else frozenset(),
        zones_executable=frozenset({scratch}) if can_exec else frozenset(),
    )


def _render_derived(run_root) -> None:
    """Re-render the derived/ transcripts + metrics from the frozen archive (§17.3).
    A read-side projection; a rendering failure must never mask the run result — but it
    must not vanish either, so the traceback is written to derived/RENDER_ERROR.txt
    rather than silently swallowed (a real archive/serialization regression stays visible)."""
    try:
        from oaos2.archive import render_archive
        render_archive(run_root)
    except Exception:  # noqa: BLE001 — convenience render, but surface the failure
        import traceback
        try:
            d = Path(run_root) / "derived"
            d.mkdir(parents=True, exist_ok=True)
            (d / "RENDER_ERROR.txt").write_text(traceback.format_exc())
        except OSError:
            pass


def _persist_run_status(run_root, cell, **facts) -> None:
    """Persist the scored outcome to ``run_status.json`` for the run registry.

    The numeric score/pass lives in ``researcher_diagnostics`` (never archived to the
    agent-facing trace), so a completed run records it here. A killed/canceled run
    never reaches this point → no status file → the registry classifies it from the
    archive's terminal record (incomplete). Best-effort; never masks the run result.
    ``facts`` are extra spine-derived keys (per-role cost/tokens, C1h)."""
    import json as _json
    try:
        status = {
            "preset_id": cell.preset_id, "model_ref": cell.model_ref,
            "role_model_refs": getattr(cell, "role_model_refs", {}),  # certified per-role binding
            **facts,
            "difficulty": getattr(cell, "difficulty", None),
            "context_budget": getattr(cell, "context_budget", None),
            "passed": cell.passed, "partial_score": cell.partial_score,
            "scored": getattr(cell, "scored", True),
            "label": cell.label, "closed": cell.closed, "archive_valid": cell.archive_valid,
            # ``label`` is the run's assisted/unassisted setting; the headline scorer's own
            # label for its verdict is kept apart under its own name
            "scorer_label": (getattr(cell, "score_detail", None) or {}).get("headline_label"),
            "cost_usd": cell.cost_usd, "parity_regime": getattr(cell, "parity_regime", None),
            "output_tokens": getattr(cell, "output_tokens", None),
            "parity_basis": getattr(cell, "parity_basis", "usd"),
            "exposure_confounded": cell.exposure_confounded,
            "rounds_total": getattr(cell, "rounds_total", None),
            "clock_label": getattr(cell, "clock_label", None),
        }
        (Path(run_root) / "run_status.json").write_text(_json.dumps(status, indent=2, sort_keys=True))
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        # Status persistence feeds the run registry; surface a failure (the registry will
        # otherwise read the run as "incomplete") rather than swallowing it blindly.
        import traceback
        try:
            (Path(run_root) / "run_status_ERROR.txt").write_text(
                f"{exc!r}\n{traceback.format_exc()}")
        except OSError:
            pass


def _pack_spine(rd, run_id: str, pack) -> RunSpine:
    """The one spine constructor for a cell: injects the pack's COMPOSED trace
    vocabularies (manifest ``trace_vocabulary`` → loader-resolved registries over
    the foundation specs, M0 §5.2) so pack event classes / phase names validate
    at emission without ever editing the foundation tables."""
    return RunSpine(rd.root, run_id=run_id,
                    event_class_registry=pack.event_class_registry,
                    phase_name_registry=pack.phase_name_registry)


def _pack_router(pack):
    """A Router over the pack's composed comm-kind registry (None = default
    foundation kinds — build_runtime constructs its own Router)."""
    if pack.comm_kind_registry is None:
        return None
    from oaos2.communication.router import Router
    return Router(kind_registry=pack.comm_kind_registry)


def _adapter_for(model_ref, *, reasoning_kind, interleaved_thinking, effort=None):
    """Pick the live transport adapter from the ``model_ref`` prefix (M7 §10).

    The provider seam is the model_ref namespace, resolved through the OPEN
    provider registry in ``models/adapters`` (register_provider_adapter — a new
    provider is an adapter module + a registration, no runner edit). The agent
    loop never branches on provider, and resolution FAILS CLOSED (audit round 8
    P2-6): an unknown or unprefixed namespace refuses rather than silently
    billing Anthropic (``typo/model`` previously resolved to the calibration
    provider). ``adapter_factory`` still overrides this entirely for tests/stubs.
    """
    from oaos2.models.adapters import registered_provider_namespaces, resolve_provider_adapter
    if "/" not in model_ref:
        raise ValueError(
            f"model_ref {model_ref!r} has no provider namespace — use "
            f"'<provider>/<model>' with provider in {sorted(registered_provider_namespaces())}")
    provider = model_ref.split("/", 1)[0]
    cls = resolve_provider_adapter(provider, model_ref=model_ref)
    # Pure namespace routing: how a provider realizes the neutral reasoning request
    # (verbatim thinking vs summaries, interleaved or not) lives in the adapter's
    # own `for_reasoning`, never here.
    # `effort` only when a role has one: registered adapters written before it existed
    # keep working for every model that takes a budget.
    return cls.for_reasoning(reasoning_kind=reasoning_kind,
                             interleaved_thinking=interleaved_thinking,
                             **({"effort": effort} if effort is not None else {}))


def _exposure_confounded_from_archive(run_root) -> bool:
    """True iff any ``model.responded`` event recorded a degraded (confounded) exposure.

    The gateway stamps ``realized_exposure.exposure_confounded`` per call (M3 §2.1); the
    cell is confounded if ANY call was. Read back from the archive (rather than threaded
    through the agent loop) so the runner stays provider-agnostic and the flag is sourced
    from the same event the auditor reads.
    """
    from oaos2.trace.invariants import load_all_events
    try:
        events = load_all_events(run_root)
    except Exception:  # noqa: BLE001 — a confound gate must fail CLOSED: if we cannot read the
        return True    # archive to rule out a degraded exposure, flag the cell rather than clear it.
    return any(
        e.get("event_class") == "model.responded"
        and (e.get("payload") or {}).get("realized_exposure", {}).get("exposure_confounded")
        for e in events
    )


# The v2 exposure-audit ask (interdependence_design.md, 2026-07-15 voice-supply re-dial):
def clock_notice_text(*, round_no: int, rounds_total: int, duty: str, checkpoints: str) -> str:
    """The daily clock notice, template-identical across arms (an apparatus constant).

    Until 2026-09-25 it also told every role that its arrived correspondence was kept on
    file under ``/work/agents/<role>/correspondence/`` and that filed submissions were on
    record in ``/work/submitted/``. No role in any clocked preset held a tool that could
    read either location (the 2026-09-24/25 audits: zero file reads in 48 confirmatory
    runs), so both sentences promised an affordance nothing could use. They are removed;
    the correspondence file itself is still written, as a research record and as the
    source of the case file's notices. The sentence that a past-window response is still
    accepted stays (possibility only; the graded half-credit rate is scoring, never
    agent-visible). ``affordances.audit_affordances`` lints this text with the role
    packets, so a future promise of an unusable record fails readiness.
    """
    return (f"[Fund clock] Day {round_no} of {rounds_total}. {duty}Checkpoints: {checkpoints}. "
            "A response filed after its stated return window is still accepted.")


async def _watch_stop(stop, rs, spine) -> None:
    """Wait for the PI's stop; record it once and retire every agent (experiments/stop.py)."""
    await stop.requested.wait()
    await spine.emit_event("run.stop_requested", payload={
        "by": "pi", "signal": stop.signal_name,
        "note": "the PI stopped the run; agents make no new model call, and the run finalizes as at a normal end"})
    rs.request_stop()


async def run_org_live(
    org_spec: OrganizationSpec,
    runs_root: Path,
    *,
    tier: str,
    run_id: str | None = None,
    model_ref: str = "anthropic/claude-sonnet-4-6",
    experiment_id: str = "exp_live",
    mode: str = "pilot",
    preregistration_ref: str | None = None,  # required (and must exist) when mode="confirmatory"
    confirmatory_evidence: dict | None = None,  # typed {capacity_calibration: {path, sha256}};
                                                # required (validated + matched) when mode="confirmatory"
    cap_usd: float = 3.0,
    cap_output_tokens: int | None = None,
    final_reserve_tokens: int = 0,  # settlement reserve inside the token pool
    parity_basis: str = "usd",
    parity_regime: str | None = None,
    reasoning_kind: str = "thinking",
    reasoning_budget: int | None = 8000,
    interleaved_thinking: bool = True,
    effort: str | None = None,  # reasoning effort for models set by an effort level rather
                                # than a budget (anthropic EFFORT_MODELS); required when a
                                # role runs one, ignored by budget models
    wall_clock_cap: int = 180,
    image_ref: str = "oaos2-science:py311",
    task_pack: str = "paper_replication",  # which task pack to load (generic; default = the calibrated one)
    max_model_calls: int = 200,
    max_output_tokens: int | None = None,  # per-call output ceiling; None = the behavior's default
    budget_pressure_frac: float | None = None,  # share of the cap at which the wrap-up notice
                                                # fires; None = the behavior's default (0.7)
    context_budget: int | None = None,  # run-level uniform per-agent context cap (sweep IV);
                                        # overrides each role's context_budget_tokens when set
    integrator_rotation: int = 0,  # D9: which role composes for a ratified deliberative arm
                                   # (index into roles, mod n) — rotated by the sweep across
                                   # replications so no frame owns composition. Never a race.
    clock_override: dict | None = None,  # per-cell ClockSpec overrides (tasks/clock.py
                                         # _OVERRIDE_KEYS: rounds_total, plan_deadline_rounds,
                                         # schedule_variant, calls_per_day, megabatch).
                                         # Validated by ClockSpec.override; requires a
                                         # CLOCKED contract profile. The sweep's horizon lever.
    clock_label: str | None = None,  # canonical clock-factor label for this cell
                                     # (factors["clock"]["name"]); carried through
                                     # CellResult/run_status and every grouping key.
    affordance_check: str = "warn",  # off | warn | strict — experiments/affordances.py:
                                     # every affordance a role is told about must be usable;
                                     # warn records findings, strict refuses to stage.
    backend=None,
    adapter_factory=None,
    design_ref: Path | str | None = None,
    resolved_sweep_plan: dict | None = None,
    stop=None,  # experiments.stop.RunStop: the PI's clean stop (a launcher's first SIGINT/SIGTERM)
) -> CellResult:
    """Execute one organization on a selected task and return its CellResult.

    Use the task's contract and registered coordination procedure, with optional
    clock settings. The default backend and adapters make this a paid Docker
    run; tests can inject simulated implementations. RunSession manages cleanup.
    See docs/RUNBOOK.md for setup and authorization requirements."""
    from oaos2.agents.model_agent import (
        DEFAULT_CACHE_POLICY,
        DELIBERATION_CACHE_POLICY,
        make_model_agent_behavior,
    )
    from oaos2.agents.tools import PAPER_TOOLSPECS, ToolContext
    from oaos2.docker.backend import LocalDockerBackend
    from oaos2.docker.policy import DockerPolicy, Mount
    from oaos2.docker.runner import stage_agent_in_docker
    from oaos2.models.raw_store import RawPayloadStore
    from oaos2.pricing.ledger import CostLedger
    from oaos2.workspace.monitor import WorkspaceManager
    from oaos2.workspace.zones import MountMode

    from oaos2.pricing.ledger import validate_spending_cap
    cap_usd = validate_spending_cap(cap_usd, allow_unbounded=False)
    org_spec.validate()  # structure load-time gate (decision-rights keys, topology, no broadening)
    # What each role's model is actually sent; refuses unusable effort settings here,
    # before any resource exists.
    role_reasoning = _role_reasoning(_role_model_refs(org_spec, model_ref),
                                     reasoning_kind=reasoning_kind,
                                     reasoning_budget=reasoning_budget, effort=effort)
    effort_recorded = any("effort" in v for v in role_reasoning.values())
    if mode == "confirmatory":
        # Confirmatory preconditions are mechanical, not author discipline (DESIGN §10.1/§24):
        # a lone confirmatory cell must be bound to an existing preregistration document,
        # exactly as a design-loaded sweep is (experiments/loader enforces the same).
        if not preregistration_ref:
            raise ValueError(
                f"confirmatory run requires a final preregistration_ref, got {preregistration_ref!r}")
        # Per-cell backstop of the sweep-level readiness gate (audit round 8
        # P1-4; hardened probe 2026-08-17): prereg FINAL + typed hash-pinned
        # capacity evidence matched to THIS cell's pack/tier/model + no
        # deferred-protection arm. A lone confirmatory cell gets no laxer a
        # gate than a design-loaded sweep.
        # A confirmatory cell runs the REAL substrate: injected test backends /
        # stub adapters would stamp runtime="raw_api" on fabricated evidence.
        if backend is not None or adapter_factory is not None:
            raise ValueError(
                "confirmatory runs refuse injected backends/adapters — the cell "
                "must run the default LocalDockerBackend and the registry-"
                "resolved provider adapter (probe 2026-08-17)")
    # ONE choreography per run, resolved from the open protocol registry
    # (coordination/base.py): the org's live_coordination.mode keys it, the
    # by-role pipeline resolves structurally, and a plugin mode registers via
    # its declared protocol_module — never a core branch here (round-8 scoped
    # milestone: runner choreography is arm semantics, not engine code).
    from oaos2.experiments.coordination import (
        CoordinationContext, make_inbound_handler, resolve_coordination_protocol)
    protocol = resolve_coordination_protocol(org_spec)
    # The org preset may pin a specific contract profile (config-as-data — the v2 arms
    # select their amendment-round profiles this way); the protocol's default stands
    # otherwise. A tier-keyed mapping ({tier: profile}) keeps ONE preset per form while
    # the contract realization follows the cell's tier (clocked per-case slots are
    # tier-derived; estimand correction 2026-08-27) — fail-closed on a missing tier.
    _profile_override = (org_spec.live_coordination or {}).get("contract_profile")
    if isinstance(_profile_override, dict):
        if tier not in _profile_override:
            raise ValueError(
                f"org preset {org_spec.preset_id!r} declares contract_profile per tier "
                f"{sorted(_profile_override)}; cell tier {tier!r} has no entry")
        _profile_override = _profile_override[tier]
    pack = load_task_pack(task_pack, decomposed=protocol.is_decomposed,
                          profile=(_profile_override or protocol.contract_profile))
    # Clocked-rounds opt-in flag (clock_design.md §7), needed before prompt
    # assembly: the duty text's continuous tail differs. The environment-driver
    # and tier pairing checks live with the driver construction below.
    # (Overrides cannot change profiles, so `clocked` is override-invariant.)
    clocked = pack.clock is not None and pack.clock.is_clocked_profile(pack.contract_profile)
    if clock_override:
        if not clocked:
            # Audit round 5 P2-5: a pack may hold batched AND clocked profiles;
            # an override against a batched profile would be silently ignored.
            raise ValueError(
                f"clock_override requires a clocked contract profile; "
                f"{pack.contract_profile!r} is batched "
                f"(clocked: {list(pack.clock.profiles) if pack.clock else []})")
        from dataclasses import replace as _dc_replace
        # Shallow pack copy with the overridden spec: cells never share or
        # mutate a loaded pack's clock (per-cell immutability, repair item 4).
        pack = _dc_replace(pack, clock=pack.clock.override(clock_override))
    if clocked != (org_spec.scheduler == "clocked_rounds"):
        raise ValueError(
            f"clocked profile/scheduler mismatch: contract_profile="
            f"{pack.contract_profile!r} but scheduler={org_spec.scheduler!r}")
    research_setup_sha = _research_setup_sha(
        pack, org_spec, tier=tier, model_ref=model_ref, context_budget=context_budget,
        cap_usd=cap_usd, cap_output_tokens=cap_output_tokens,
        final_reserve_tokens=final_reserve_tokens, parity_basis=parity_basis,
        reasoning_kind=reasoning_kind, reasoning_budget=reasoning_budget,
        interleaved_thinking=interleaved_thinking, max_model_calls=max_model_calls,
        wall_clock_cap=wall_clock_cap, image_ref=image_ref,
        integrator_role=protocol.integrator_role(org_spec, pack, integrator_rotation),
        effort=effort)
    if mode == "confirmatory":
        from oaos2.experiments.confirmatory import assert_confirmatory_ready, ConfirmatoryReadinessError
        if not _source_state().get("source_code_sha256"):
            raise ConfirmatoryReadinessError("confirmatory execution requires readable executable-source identity")
        assert_confirmatory_ready(
            org_specs=[org_spec], preregistration_ref=preregistration_ref,
            evidence=confirmatory_evidence, task_pack=task_pack,
            model_refs=_launch_model_refs((model_ref,), [org_spec]), tiers=(tier,),
            setup_sha256s=(research_setup_sha,))
    if run_id is None:
        from oaos2.experiments.naming import run_id as _make_run_id
        run_id = _make_run_id(preset=org_spec.preset_id, difficulty=tier, model_ref=model_ref, rep=1)
    rd = RunDir.create(runs_root, experiment_id, pack.pack_id, run_id)
    (rd.visible / "data").mkdir(parents=True, exist_ok=True)
    data_mounts = [Mount(pack.data_mount_source(), "/visible/data", MountMode.RO)]
    # Explicit lifecycle (experiments/session.py, repair item 5): every check
    # below runs in the preflight phase — the session structurally refuses to
    # attach resources until preflight_ok(), so a refused run stages nothing.
    from oaos2.experiments.session import RunSession
    session = RunSession(rd, run_id)

    # Environment driver + every clocked validation run BEFORE the spine or any
    # container exists (audit round 4 P1-4): a refused preflight must leak
    # nothing. Dispatch modes stay exclusive (stamp-only in clocked runs).
    from oaos2.environment import build_environment_driver, dispatch_after_commit
    environment_driver = build_environment_driver(
        pack.environment, tier,
        variant=(pack.clock.schedule_variant if clocked else None))
    if clocked:
        if environment_driver is None:
            raise ValueError("clocked run requires an environment schedule")
        # Every temporal invariant is the ClockSpec's to check (tasks/clock.py):
        # tier pairing + horizon/coverage/fuse preflight, before any resource.
        pack.clock.validate_tier(tier, pack.contract_profile)
        pack.clock.validate_schedule(environment_driver)
    if environment_driver is not None:
        # Self-contained archives (audit round 2 P1-2): the exact schedule this
        # run dispatched from, verified downstream against the same manifest
        # pin. Host-side config dir, never mounted.
        (rd.config / "environment_schedule.json").write_bytes(
            Path(environment_driver.schedule_path).read_bytes())

    table = _pricing_table_for(_role_model_refs(org_spec, model_ref).values())
    retention = RetentionPolicy()
    retention.validate_for_mode(RunMode(mode))  # confirmatory pins the full-fidelity floor (§17.3)
    resolved_sweep_sha = _write_resolved_sweep(rd, resolved_sweep_plan)
    # Both breakpoint policies (main loop + deliberation volleys) enter the fingerprint —
    # the confound gate (M3 §3.1) must trip if EITHER differs across compared cells.
    cache_fp = f"{DEFAULT_CACHE_POLICY.fingerprint()}:{DELIBERATION_CACHE_POLICY.fingerprint()}"
    # D9 markers (pinned in the manifest + drive the staging hooks): the protocol
    # designates its rotated composer when the form has one (deliberative RATIFIED
    # profiles) — composition is never a race.
    integrator_id = protocol.integrator_role(org_spec, pack, integrator_rotation)
    # Per-role EFFECTIVE model binding (C1h): declared here, bound in the staging
    # loop below, certified against `model.invoked` after the cell closes.
    role_model_refs = _role_model_refs(org_spec, model_ref)
    model_heterogeneous = len(set(role_model_refs.values())) > 1
    manifest = Manifest(
        run_id=run_id, experiment_id=experiment_id, task_pack_id=pack.pack_id, mode=mode,
        pricing_table_version=table.version, organization_id=org_spec.preset_id,
        retention_policy_hash=_sha256_json(retention.model_dump()),
    )
    manifest.extensions.update({
        "research_setup_sha256": research_setup_sha,
        "pricing_table_hash": table.hash(), "reference_sha256": _headline_ref_sha(pack, tier),
        "model_ref": model_ref, "difficulty": tier, "cap_usd": cap_usd,
        "role_model_refs": role_model_refs, "model_heterogeneous": model_heterogeneous,
        "cap_output_tokens": cap_output_tokens,
        "final_reserve_tokens": (final_reserve_tokens
                                 if cap_output_tokens is not None else 0),
        "parity_basis": parity_basis,
        "parity_regime": parity_regime,
        "resolved_sweep_ref": ("config/resolved_sweep.json"
                               if resolved_sweep_sha is not None else None),
        "cache_policy_fingerprint": cache_fp, "cache_breakpoints": list(DEFAULT_CACHE_POLICY.breakpoints),
        "cache_ttl_overrides": dict(DEFAULT_CACHE_POLICY.ttl_overrides),
        "deliberation_cache_breakpoints": list(DELIBERATION_CACHE_POLICY.breakpoints),
        "deliberation_cache_ttl_overrides": dict(DELIBERATION_CACHE_POLICY.ttl_overrides),
        "decomposed_contract": protocol.is_decomposed, "n_agents": org_spec.n_agents,
        "integrator_role": integrator_id,  # D9 rotated composer (None outside the ratified organic arm)
        "reasoning_kind": reasoning_kind,
        "reasoning_interleaved": bool(interleaved_thinking and reasoning_kind == "thinking"),
        **({"effort": effort, "role_reasoning": role_reasoning} if effort_recorded else {}),
        "missing_optional_refs": list(pack.missing_optional_refs),  # scoring-degradation audit (M7 §2.2)
        "retention_policy": retention.model_dump(),
        "preregistration_ref": preregistration_ref,
        **_apparatus_pins(pack, org_spec, tier=tier,
                          preregistration_ref=preregistration_ref, design_ref=design_ref,
                          resolved_sweep_sha256=resolved_sweep_sha),
    })
    manifest.write(rd.manifest_path)
    _write_config_snapshot(rd, {
        "task_pack_id": pack.pack_id, "difficulty": tier, "organization": org_spec.preset_id,
        "model_ref": model_ref, "reasoning_kind": reasoning_kind, "reasoning_budget": reasoning_budget,
        "role_model_refs": role_model_refs, "model_heterogeneous": model_heterogeneous,
        "reasoning_interleaved": bool(interleaved_thinking and reasoning_kind == "thinking"),
        **({"effort": effort, "role_reasoning": role_reasoning} if effort_recorded else {}),
        "parity_basis": parity_basis, "cap_usd": cap_usd,
        "cap_output_tokens": cap_output_tokens,
        "final_reserve_tokens": (final_reserve_tokens
                                 if cap_output_tokens is not None else 0),
        "parity_regime": parity_regime,
        "resolved_sweep_sha256": resolved_sweep_sha,
        "max_model_calls": max_model_calls,
        "context_budget": context_budget,  # per-agent context cap (sweep IV; None = unbounded)
        "cache_policy_fingerprint": cache_fp, "decomposed_contract": protocol.is_decomposed,
        "outcome_contract": pack.outcome_contract.outcome_id, "n_agents": org_spec.n_agents,
        "evaluator": next((ev.evaluator_ref for ev in pack.evaluators.values()
                           if getattr(ev, "produces_headline_score", False)), None),
        "reference_sha256": _headline_ref_sha(pack, tier),
        "roles": [{"role_id": r.role_id, "plays": r.plays, "specialized": r.specialized}
                  for r in org_spec.roles],
    })

    if clocked:
        # Contract ↔ schedule consistency is a PREFLIGHT check (audit round 5
        # P1-3): a malformed timing declaration must refuse the run before any
        # container stages. The clocked block below re-binds against the
        # coordinator's contract copy (same ids, cheap).
        pack.clock.bind(pack.outcome_contract, environment_driver.case_rounds(),
                        _update_rounds(environment_driver))

    # Resolve the per-role commitment binding + the handoff chain in PREFLIGHT
    # (audit round 6 P1-2): a role with no contract binding must refuse the run
    # before the spine exists — the ids are contract data, resource-free. The
    # chain's shape is the protocol's (coordination/, one module per form).
    from oaos2.experiments.coordination import role_commitment_seq as _rcs

    def _role_commitment_seq(role) -> list:
        # The generic advance/ceiling/clock machinery below shares the protocol
        # layer's ordering rule (coordination/base.py) — one definition, one seam.
        return _rcs(org_spec, pack.outcome_contract, role)

    chain = protocol.build_chain(org_spec, pack.outcome_contract)

    # Readiness: no dead affordances (2026-09-25). Lint each role's resolved prompt and
    # the standing clock notice for promises the role cannot act on; record the findings
    # in the run's config; refuse to stage under "strict".
    if affordance_check not in ("off", "warn", "strict"):
        raise ValueError(f"affordance_check must be off|warn|strict, got {affordance_check!r}")
    if affordance_check != "off":
        from oaos2.experiments.affordances import audit_affordances, findings_as_json
        _notice = ({"clock": clock_notice_text(round_no=1, rounds_total=1, duty="", checkpoints="")}
                   if clocked else {})
        _findings = audit_affordances(org_spec, pack, tier, notice_texts=_notice)
        (rd.config / "affordance_audit.json").write_text(json.dumps(
            {"mode": affordance_check, "findings": findings_as_json(_findings)}, indent=2))
        if _findings and affordance_check == "strict":
            raise ValueError(
                "affordance audit: roles are told of affordances they cannot use: "
                + "; ".join(f"{f.role_id}:{f.kind}:{f.promise} ({f.reason}; {f.source})" for f in _findings))

    session.preflight_ok()  # every validation above passed; resources may exist
    # Backend inspection and policy construction precede the spine (audit
    # round 5 P1-3): a failure here must not leave an unfinalized trace. The
    # spine attaches to the session the moment it starts, so every subsequent
    # failure flows through session.abort (terminal record guaranteed).
    backend = backend or LocalDockerBackend()
    # A pack whose selected issue set pins an environment (python_bug_repair, M8 §9)
    # runs the agent in that image when the organization selects the container
    # grader: the sweep path passes no image, and the science image lacks the
    # library's test dependencies. An explicit non-default image_ref still wins.
    _lc = org_spec.live_coordination or {}
    if _lc.get("grader_backend") == "container" and image_ref == "oaos2-science:py311":
        _sets = dict((getattr(pack, "repair_spec", None) or {}).get("issue_sets") or {})
        _set = _lc.get("issue_set") or (getattr(pack, "repair_spec", None) or {}).get("default_set")
        _env = dict((_sets.get(_set) or {}).get("environment") or {})
        if _env.get("image"):
            image_ref = str(_env["image"])
    digest = backend.inspect_digest(image_ref)
    policy = DockerPolicy(
        image_ref=image_ref, image_digest_pinned=digest, network_policy="disabled",
        hidden_host_paths=[pack.hidden_dir], wall_clock_limit=max(wall_clock_cap, 1800),
        env_allowlist={"HOME": "/tmp", "MPLCONFIGDIR": "/tmp", "XDG_CACHE_HOME": "/tmp"},
    )
    spine = _pack_spine(rd, run_id, pack)
    await spine.start()
    session.attach_resources(spine=spine, backend=backend, policy=policy)
    # Session-owned setup boundary (audit round 6 P1-2): EVERY operation
    # between spine start and the supervised execution block aborts through
    # the session — teardown of whatever staged, spine finalized 'failed',
    # never an empty unterminated trace.
    try:
        # Docker identity is only resolvable after backend inspection. Rewrite the manifest
        # before any agent is staged so the run identity card and trace agree.
        manifest.image_ref = image_ref
        manifest.image_digest = digest
        manifest.policy_hash = policy.hash()
        manifest.write(rd.manifest_path)

        wm = WorkspaceManager(rd, spine)
        coordinator = OutcomeCoordinator(copy.deepcopy(pack.outcome_contract), spine, rd.submitted)
        ledger = CostLedger(pricing_table=table, cap_usd=cap_usd,
                            cap_output_tokens=cap_output_tokens,  # ONE shared cell budget
                            final_reserve_tokens=(final_reserve_tokens
                                                  if cap_output_tokens is not None else 0))
        store = RawPayloadStore(rd.root)

        tool_ctxs = []
        tc_by_role: dict = {}  # role_id -> ToolContext (the D9 coordination tasks advance bindings)
        # The protocol's closure surface (coordination/base.py): tc_by_role is shared
        # by reference (fills during staging); rs attaches after build_runtime.
        ctx = CoordinationContext(
            org_spec=org_spec, pack=pack, coordinator=coordinator, chain=chain,
            clocked=clocked, integrator_rotation=integrator_rotation,
            integrator_id=integrator_id, spine=spine, tc_by_role=tc_by_role,
            backend=backend, policy=policy, session=session, run_dir=rd)

        async def _no_slot_handler(_role_id: str, _slot_id: str) -> bool:
            return False  # no coordination installed: slot stays open, deadlock backstop applies

        _slot_ceiling_impl: dict = {"handler": _no_slot_handler}  # late-bound §11.6 handler
        agents = []
        readiness_by_role: dict = {}  # agent_id -> blocks-readiness predicate (scheduler admission)
        realized_reasoning_kind: dict = {}  # role_id -> provider-realized reasoning surface (C1h)

        for i, (role, commit_id) in enumerate(chain):
            try:
                handle = await stage_agent_in_docker(spine, backend, rd, role.role_id, policy,
                                                     extra_ro_mounts=data_mounts,
                                                     omit_mounts=tuple(getattr(pack, "container_mounts_omit", ())))
            except BaseException as exc:  # mid-fleet staging failure (Docker flakiness is real)
                await session.abort(exc)  # tears down the already-staged fleet, finalizes failed
            session.register_handle(handle)
            packet_role = role.role_packet or role.role_id  # config-declared; defaults to role_id
            system_prompt, user_text = pack.build_initial_prompt(
                tier, role=packet_role, attention=role.attention, tools=role.tools)
            if protocol.initial_duty_in_prompt or pack.staged_coordination.get("auto_advance"):
                user_text += "\n" + _commitment_duty(coordinator.contract, commit_id,
                                                  continuous=clocked)
            (rd.config / f"prompt_envelope_{role.role_id}.json").write_text(json.dumps({
                "agent_id": role.role_id, "role_packet": packet_role, "commitment": commit_id,
                "tier": tier, "system_prompt": system_prompt, "initial_user_text": user_text,
            }, indent=2))
            tool_ctx = ToolContext(
                agent_id=role.role_id, rs=None, backend=backend, handle=handle, run_dir=rd,
                coordinator=coordinator, submit_commitment_id=commit_id, wall_clock_cap=wall_clock_cap,
                python_timeout_s=(org_spec.live_coordination or {}).get("python_timeout_s"),
                # The contract's final scored commitment: calls made under this binding are
                # exempt from the token pool's settlement reserve (ledger, 2026-07-17).
                final_commitment_id=coordinator.contract.commitments[-1].commitment_id,
                disk_limit=policy.disk_limit,
                allowed_tools=(set(role.tools) if role.tools is not None else None),  # hard dispatch gate
                file_access_policy=_role_file_policy(role),  # per-role zone ACL (DESIGN §18.1, §8)
                decision_rights=role.decision_rights,  # submit authority (None ⇒ permissive)
            )
            tool_ctxs.append(tool_ctx)
            tc_by_role[role.role_id] = tool_ctx  # the coordination tasks advance bindings (D9)

            # The protocol's per-role choreography: admission gate, inbound
            # rendering, post-submit handoffs (coordination/, one module per
            # form; a gate registered here withholds scheduler admission).
            hooks = protocol.role_hooks(ctx, i, role, commit_id, tool_ctx)
            readiness, inbound, post_submit = hooks.readiness, hooks.inbound, hooks.post_submit
            if readiness is not None:
                readiness_by_role[role.role_id] = readiness
                # The behavior's own yield gate must see the SAME gate the scheduler
                # uses, including the clocked wraps installed later (arrival; a pending
                # query, 2026-09-25) — look it up at call time, never capture it now.
                readiness = (lambda rid=role.role_id: readiness_by_role[rid]())
            role_seq = _role_commitment_seq(role)
            if inbound is None and pack.staged_coordination.get("auto_advance"):
                # Plain-staged solo/ensemble arms (no coordination branch below): the
                # platform's stage_assignment duty notices are DELIVERED on every binding
                # advance but were rendered only by the multi-agent branches' inbound
                # handlers — a solo agent's next-slot announcement drained into the void,
                # so it had to guess the slot and payload shape (calibration round 2b
                # death, 2026-08-12). The initial prompt promises "the platform will
                # announce any later slot"; make that true for every arm.
                inbound = make_inbound_handler()

            # Per-role tool policy (DESIGN §18.1): offer the model only the tools the role may
            # use. Restricting the reader/reviewer to read-only inspection means the model
            # literally cannot run the analysis — it must specify/review (enforced, not asked).
            role_toolspecs = (PAPER_TOOLSPECS if role.tools is None
                              else [t for t in PAPER_TOOLSPECS if t.name in set(role.tools)])
            # Registered task actions (M8 §2): offered ONLY when the role's grant
            # names them; the same names sit in allowed_tools, so dispatch enforces
            # the grant exactly as for built-ins.
            role_actions = ({name: a for name, a in pack.actions.items()
                             if role.tools is not None and name in set(role.tools)})
            # The pack's own descriptions for built-in tools (manifest `tool_descriptions`):
            # apparatus text, identical for every role and arm (realism review 2026-09-25).
            from oaos2.agents.tools import apply_tool_descriptions
            role_toolspecs = apply_tool_descriptions(role_toolspecs, pack.tool_descriptions)
            role_toolspecs = list(role_toolspecs) + [a.toolspec() for a in role_actions.values()]
            tool_ctx.task_actions = role_actions or None
            # The budget notice's wording (model_agent.cost_pressure_text): "plain" states the facts without telling
            # the laboratory to submit (PC1 x7, October 18, 2026); unset keeps the older text.
            tool_ctx.cost_notice = (org_spec.live_coordination or {}).get("cost_notice")
            # Per-role binding (C1h): the role's own ref wins, else the run-level
            # factor; each provider realizes the SAME neutral reasoning request
            # natively (its own `for_reasoning`) — no LCD equalization here.
            effective_ref = role_model_refs[role.role_id]
            adapter = (_adapter_from_factory(adapter_factory, effective_ref)
                       if adapter_factory is not None
                       else _adapter_for(effective_ref, reasoning_kind=reasoning_kind,
                                         interleaved_thinking=interleaved_thinking,
                                         effort=role_reasoning[role.role_id].get("effort")))
            realized_reasoning_kind[role.role_id] = _realized_reasoning_kind(adapter, reasoning_kind, effective_ref)
            behavior = make_model_agent_behavior(
                adapter=adapter, model_ref=effective_ref, system_prompt=system_prompt,
                initial_user_text=user_text, toolspecs=role_toolspecs, tool_context=tool_ctx,
                ledger=ledger, raw_store=store, reasoning_kind=reasoning_kind,
                # an effort model refuses any budget; budget models keep the run's own
                reasoning_budget=(None if "effort" in role_reasoning[role.role_id]
                                  else reasoning_budget),
                max_model_calls=max_model_calls,
                **({"max_output_tokens": max_output_tokens} if max_output_tokens is not None else {}),
                **({"budget_pressure_frac": budget_pressure_frac}
                   if budget_pressure_frac is not None else {}),
                compaction_instruction=pack.compaction_instruction,  # pack-declared; None = default
                inbox_heading=getattr(pack, "inbox_heading", None),
                compaction_max_tokens=pack.compaction_max_tokens,
                compaction_max_chars=pack.compaction_max_chars,
                context_budget_basis=str((org_spec.live_coordination or {}).get("context_budget_basis") or "estimate"),
                context_budget_tokens=(context_budget if context_budget is not None
                                       else role.context_budget_tokens),
                confirmatory=(mode == "confirmatory"),
                deliberation=protocol.is_deliberative,  # organic arm: produce conversation volleys when holding the floor
                deliberation_instruction=pack.deliberation_instruction,  # pack-declared (D6); None = default
                readiness_gate=readiness, inbound_handler=inbound, post_submit_messages=post_submit,
                # §11.6 per-slot capacity: declared ⇒ enforced, in EVERY arm
                # (config-as-data). The staged-only gate silently dropped the solo
                # arm's declared 8-call cap while the org arms' caps bound —
                # contradicting the arm-identical capacity constants the clocked
                # interpretation rests on (audit 2026-08-15 round 2, P1-1). The
                # handler is installed after the coordination closures exist
                # (late-bound via the dict); without one, the slot stays open and
                # the deadlock backstop is the honest end.
                max_calls_per_slot=role.max_calls_per_slot,
                slot_ceiling_handler=(
                    (lambda slot, rid=role.role_id:
                     _slot_ceiling_impl["handler"](rid, slot))
                    if role.max_calls_per_slot is not None else None),
                # Stage-aware retirement (D9): retire only after the role's LAST commitment
                # (single-commitment roles: identical to the legacy retire-on-submit).
                # A procedure may supply both continuation hooks (M8 §1); the
                # defaults derive retirement from the role's fixed sequence and
                # continuation from clocked megabatching.
                retire_after_submit=(
                    hooks.retire_after_submit if hooks.retire_after_submit is not None
                    # An office in an exchange preset (send_reply granted) stays until the
                    # run closes: the center may query it after its last filing (2026-09-25).
                    # It idles unless the pending-query gate admits it.
                    else ((lambda: False) if "send_reply" in set(role.tools or ()) else
                          (lambda tc=tool_ctx, last=(role_seq[-1] if role_seq else None):
                           last is None or tc.last_submitted_commitment_id == last))),
                # Clocked megabatching: continue in-turn only onto a duty the
                # arrival-aware readiness gate says is actionable NOW (the gate is
                # installed in readiness_by_role after staging; read at call time).
                continue_after_submit=(
                    hooks.continue_after_submit if hooks.continue_after_submit is not None
                    else ((lambda rid=role.role_id:
                           (lambda g: g is not None and g())(
                               readiness_by_role.get(rid)))
                          if clocked and pack.clock.megabatch else None)),
                # Fixed daily leadership capacity (audit round 3 P1-2): a hard
                # per-role per-round model-call ceiling, identical in every arm;
                # megabatching lives inside it. Batched runs: unbounded per turn.
                max_calls_per_turn=((role.calls_per_day or pack.clock.calls_per_day) if clocked else None),
            )
            agents.append(make_agent(role.role_id, behavior, role_id=role.role_id))

        # Recorded, not equalized (C1h): a mixed org realizes ONE neutral request on
        # two surfaces; nothing is exposed to the agent, so no LCD refusal applies.
        manifest.extensions["realized_reasoning_kind"] = dict(sorted(realized_reasoning_kind.items()))
        manifest.write(rd.manifest_path)

        rs = build_runtime(spine, agents, scheduler=org_spec.scheduler, workspace=wm,
                           router=_pack_router(pack))
        rs.max_actions_per_turn = max_model_calls + 5
        ctx.rs = rs  # the protocol's orchestration closures read it at await time
        stop_watch = (asyncio.create_task(_watch_stop(stop, rs, spine)) if stop is not None else None)
        # The form's declared handoff topology (M6 §1): a handoff outside the
        # protocol's contract is refused; None = no formal handoff channel.
        _handoff_contract = protocol.handoff_contract(ctx)
        if _handoff_contract is not None:
            rs.handoff_contract = _handoff_contract
        rs.readiness.update(readiness_by_role)  # dependency-driven admission (no finish_turn spin)
        rs.environment_scopes = {r.role_id: _packet_scope(r) for r in org_spec.roles}
        # Organization-structure surface (M5 §18.1): the org topology + per-role decision
        # rights enforced at the handoff/submit seams. None/{} for the four arms (permissive).
        rs.topology = org_spec.topology
        rs.decision_rights = {r.role_id: r.decision_rights for r in org_spec.roles
                              if r.decision_rights is not None}
        rs.comm_kinds = {r.role_id: frozenset(r.comm_kinds) for r in org_spec.roles
                         if r.comm_kinds is not None}
        for tc in tool_ctxs:
            tc.rs = rs
        coordinator.on_close = rs.close_outcome

        # Generic staged observations + stage advance.  A task opts in through its
        # manifest; the driver itself was built and validated pre-staging above.
        auto_advance = bool(pack.staged_coordination.get("auto_advance"))
        # Late-bound clocked hook: shared-committer slots (a lateral disposition may
        # be committed by EITHER peer) leave the co-bound role's linear binding
        # pointing at a committed slot; the clocked block installs a sync that hops
        # every role forward to its first uncommitted duty after any commit.
        _clocked_impl: dict = {"sync": None, "due_suffix": lambda cid: ""}
        if environment_driver is not None or auto_advance:
            async def _after_stage_commit(commitment_id, state_commitment, committed_event):
                from oaos2.communication.mailbox import MailboxItem
                from oaos2.kernel.runtime import _deliver
                from oaos2.ulid import new_ulid

                delivered = []
                if environment_driver is not None and not clocked:
                    delivered = await dispatch_after_commit(
                        environment_driver, commitment_id=commitment_id,
                        runtime_state=rs, caused_by=committed_event,
                    )
                if auto_advance and state_commitment.agent_id in tc_by_role:
                    role = next(r for r in org_spec.roles if r.role_id == state_commitment.agent_id)
                    sequence = _role_commitment_seq(role)
                    if commitment_id in sequence:
                        index = sequence.index(commitment_id)
                        if index + 1 < len(sequence):
                            next_id = sequence[index + 1]
                            tc_by_role[state_commitment.agent_id].advance_submit_binding(next_id)
                            advanced = await spine.emit_event(
                                "coordination.stage_advanced", agent_id=state_commitment.agent_id,
                                caused_by=delivered or committed_event,
                                payload={"agent_id": state_commitment.agent_id,
                                         "from": commitment_id, "to": next_id,
                                         "phase": "environment_stage"},
                            )
                            await _deliver(MailboxItem(
                                item_id=new_ulid(), kind="stage_assignment",
                                payload=_commitment_duty(coordinator.contract, next_id,
                                                         continuous=clocked)
                                + _clocked_impl["due_suffix"](next_id)
                                + _case_file_text(rs, next_id, state_commitment.agent_id),
                                source_event_id=advanced,
                            ), state_commitment.agent_id, rs)
                            rs.kick_scheduler()
                # A slot bound BEFORE its blockers committed carried an empty case file
                # (the first case of a wave binds when the plan commits). When this
                # commit completes its blockers, re-deliver the case file so the duty
                # opens with the case's records in front of the committer.
                for role_id, tc in tc_by_role.items():
                    slot = tc.submit_commitment_id
                    if slot in coordinator.committed or slot == commitment_id:
                        continue
                    try:
                        blocks = list(coordinator.contract.commitment(slot).blocks)
                    except Exception:  # noqa: BLE001 — not a commitment id
                        continue
                    if commitment_id not in blocks or not all(b in coordinator.committed for b in blocks):
                        continue
                    case_file = _case_file_text(rs, slot, role_id)
                    if case_file:
                        await _deliver(MailboxItem(
                            item_id=new_ulid(), kind="stage_assignment",
                            payload=(f"# Current commitment\nYour currently authorized submission "
                                     f"is `{slot}`; every record it waits on has now been committed."
                                     + _clocked_impl["due_suffix"](slot) + case_file),
                            source_event_id=committed_event,
                        ), role_id, rs)
                        rs.kick_scheduler()
                if _clocked_impl.get("exchange") is not None:
                    await _clocked_impl["exchange"].on_commit(
                        rs, commitment_id, _clocked_impl["slot_case"].get(commitment_id), committed_event)
                if _clocked_impl["sync"] is not None:
                    await _clocked_impl["sync"](delivered or committed_event)
            coordinator.on_commit = _after_stage_commit

            # §11.6 per-slot capacity handler: at a role's slot ceiling, record the
            # constraint and close the slot through the contract-declared fallback so the
            # organization proceeds carrying the capacity failure's consequences (referred
            # exceptions score as unresolved) — the theorized overload made mechanical.
            # A slot with NO declared fallback stays open; the deadlock backstop is then
            # the honest, loud end of the cell.
            async def _slot_ceiling_handler(role_id: str, slot_id: str) -> bool:
                from oaos2.communication.mailbox import MailboxItem
                from oaos2.kernel.runtime import _deliver
                from oaos2.ulid import new_ulid
                if slot_id in coordinator.committed:
                    return True  # raced with a successful submit; nothing to do
                commitment = coordinator.contract.commitment(slot_id)
                fallback_spec = (commitment.submission or {}).get("ceiling_fallback")
                role = next(r for r in org_spec.roles if r.role_id == role_id)
                ev = await spine.emit_event(
                    "capacity.slot_ceiling", agent_id=role_id,
                    payload={"commitment_id": slot_id,
                             "max_calls_per_slot": role.max_calls_per_slot,
                             "fallback_declared": bool(fallback_spec)})
                if not fallback_spec:
                    return False
                payload = _build_ceiling_fallback(fallback_spec, coordinator, commitment)
                committed = await coordinator.commit(
                    commitment_id=slot_id, payload=payload, agent_id="coordination",
                    session_id="coordination", caused_by=ev)
                if committed is None:
                    return False  # refused at the gate — loud, never smuggled
                # A platform commit does not trip the role auto-advance (agent_id is
                # "coordination"): advance the starved role's binding here, mirroring
                # _after_stage_commit, so the organization moves to its next slot.
                sequence = _role_commitment_seq(role)
                if slot_id in sequence:
                    index = sequence.index(slot_id)
                    if index + 1 < len(sequence):
                        next_id = sequence[index + 1]
                        tc_by_role[role_id].advance_submit_binding(next_id)
                        advanced = await spine.emit_event(
                            "coordination.stage_advanced", agent_id=role_id, caused_by=ev,
                            payload={"agent_id": role_id, "from": slot_id, "to": next_id,
                                     "phase": "capacity_fallback"})
                        await _deliver(MailboxItem(
                            item_id=new_ulid(), kind="stage_assignment",
                            payload=_commitment_duty(coordinator.contract, next_id,
                                                     continuous=clocked)
                            + _clocked_impl["due_suffix"](next_id)
                            + _case_file_text(rs, next_id, role_id),
                            source_event_id=advanced,
                        ), role_id, rs)
                rs.kick_scheduler()
                return True

            _slot_ceiling_impl["handler"] = _slot_ceiling_handler

        if clocked:
            # ------------------------------------------------------------------ #
            # Clocked rounds (decision (c)): arrival dispatch, arrival-aware
            # admission, per-case fuse + plan-deadline forcing, and the per-round
            # duty notice. All timing is instrument data: case fuses ride the
            # schedule stamps, plan deadlines ride the pack's `clock:` section.
            # ------------------------------------------------------------------ #
            from oaos2.communication.mailbox import MailboxItem
            from oaos2.kernel.clock import ClockState
            from oaos2.kernel.runtime import _deliver
            from oaos2.ulid import new_ulid

            rounds_total = pack.clock.rounds_total
            plan_deadlines: dict[str, int] = dict(pack.clock.plan_deadline_rounds)
            case_rounds = environment_driver.case_rounds()
            # Slot maps bind through each commitment's declared `timing` metadata
            # (tasks/clock.py) — the platform never parses commitment names.
            update_rounds = _update_rounds(environment_driver)
            bindings = pack.clock.bind(coordinator.contract, case_rounds, update_rounds)
            review_slots = {rid: case for case, rid in bindings.review_id.items()}
            disposition_id = bindings.disposition_id
            slot_case = bindings.slot_case
            slot_due = bindings.slot_due
            contract_ids = [c.commitment_id for c in coordinator.contract.commitments]

            # Absolute due day on every stage assignment (audit round 2, P1-3):
            # a role advanced mid-round must see its new duty's deadline even
            # though its day notice was composed at round open.
            _clocked_impl["due_suffix"] = (
                lambda cid: (f" This duty is due by day {slot_due[cid]}."
                             if cid in slot_due else ""))

            arrived_cases: set[str] = set()
            arrived_updates: set[str] = set()   # cases whose later notice has arrived
            fuse_lapsed: set[str] = set()
            review_lapsed: set[str] = set()

            # Arrival-aware admission: a role bound to a case slot idles until the
            # case's packets have arrived — idle lanes are how the clock
            # fast-forwards. Wrapped over the staged readiness gates built above.
            final_commitment_id = contract_ids[-1]

            def _arrival_gate(base, tc, role_id):
                def gate():
                    if base is not None and not base():
                        return False
                    cid = tc.submit_commitment_id
                    if cid == final_commitment_id:
                        # Closure gate (audit 2026-08-15 P1-1): the final plan is
                        # actionable only once every scheduled packet has arrived —
                        # otherwise a batching run can close while a trailing
                        # rule-covered packet (which holds no case slot) is still
                        # scheduled, and the archive fails completeness at teardown.
                        if not environment_driver.fully_dispatched():
                            return False
                    if cid in bindings.due_with_ids:
                        # Period-record gate (2026-08-30 low-tier probe forensic):
                        # a {due_with}-timed slot (period rule log / office plan)
                        # admits only once the committing role's scheduled mail
                        # through its due round has arrived. Idle lanes otherwise
                        # race the slot and certify an empty period before the
                        # period's notices exist — a truthful-at-writing report
                        # that per-period crediting can never repair. Scope
                        # resolution mirrors delivery exactly.
                        scope = rs.environment_scopes.get(role_id, role_id)
                        if environment_driver.pending_for_scope(
                                scope, slot_due[cid]):
                            return False
                    case = slot_case.get(cid)
                    if cid in review_slots:
                        # a review is actionable only once the later notice exists
                        return case in arrived_updates
                    return case is None or case in arrived_cases
                return gate

            for role_id, tc in tc_by_role.items():
                wrapped = _arrival_gate(readiness_by_role.get(role_id), tc, role_id)
                readiness_by_role[role_id] = wrapped
                rs.readiness[role_id] = wrapped  # rs copied the gates before this block

            async def _sync_bindings(caused_by, phase: str = "binding_sync") -> None:
                """Hop every role whose current binding is already committed (by a
                peer on a shared slot, or by a platform force-commit) forward to
                its first uncommitted duty — one stage_advanced event per hop set.
                The linear per-role binding stays the choreography; this only skips
                slots that no longer need the role."""
                for role in org_spec.roles:
                    tc = tc_by_role[role.role_id]
                    current = tc.submit_commitment_id
                    if current not in coordinator.committed:
                        continue
                    sequence = _role_commitment_seq(role)
                    if current not in sequence:
                        continue
                    index = sequence.index(current)
                    next_id = None
                    for candidate in sequence[index + 1:]:
                        if candidate not in coordinator.committed:
                            next_id = candidate
                            break
                    if next_id is None:
                        continue
                    tc.advance_submit_binding(next_id)
                    advanced = await spine.emit_event(
                        "coordination.stage_advanced", agent_id=role.role_id,
                        caused_by=caused_by,
                        payload={"agent_id": role.role_id, "from": current,
                                 "to": next_id, "phase": phase})
                    closed_line = (
                        f"The platform has closed `{current}` (its deadline "
                        "passed); it needs nothing further from you.\n"
                        if phase == "deadline_lapse" else "")
                    await _deliver(MailboxItem(
                        item_id=new_ulid(), kind="stage_assignment",
                        payload=closed_line
                        + _commitment_duty(coordinator.contract, next_id,
                                           continuous=clocked)
                        + _clocked_impl["due_suffix"](next_id)
                        + _case_file_text(rs, next_id, role.role_id),
                        source_event_id=advanced,
                    ), role.role_id, rs)
                rs.kick_scheduler()

            _clocked_impl["sync"] = _sync_bindings

            async def _force_slot(cid: str, caused_by: str, phase: str) -> None:
                """Close an open slot through its contract-declared fallback —
                the deadline analogue of the slot-ceiling fallback. A slot with no
                declared fallback stays open (the deadlock backstop is then the
                honest end of the cell)."""
                if cid in coordinator.committed:
                    return
                commitment = coordinator.contract.commitment(cid)
                fallback_spec = (commitment.submission or {}).get("ceiling_fallback")
                if not fallback_spec:
                    return
                payload = _build_ceiling_fallback(fallback_spec, coordinator, commitment)
                committed = await coordinator.commit(
                    commitment_id=cid, payload=payload, agent_id="coordination",
                    session_id="coordination", caused_by=caused_by)
                if committed is not None:
                    await _sync_bindings(caused_by, phase)

            async def _on_round(round_no: int) -> None:
                round_ev = await spine.emit_event(
                    "clock.round",
                    payload={"round_no": round_no, "rounds_total": rounds_total})
                from oaos2.environment import dispatch_at_round
                await dispatch_at_round(environment_driver, round_no=round_no,
                                        runtime_state=rs, caused_by=round_ev)
                arrived_updates.update(c for c, r in bindings.review_arrival.items() if r <= round_no)
                arrived_updates.update(c for c, u in update_rounds.items() if u["arrival"] <= round_no)
                if _clocked_impl.get("exchange") is not None:
                    await _clocked_impl["exchange"].on_round(rs, round_no, round_ev)
                arrived_cases.update(c for c, r in case_rounds.items()
                                     if r["arrival"] <= round_no)
                # A review's fuse lapses like a case's: marked, not forced; the
                # final plan's deadline closes what is still open.
                for case, rid in sorted(bindings.review_id.items()):
                    fuse = slot_due.get(rid)
                    if (fuse is None or round_no <= fuse or case in review_lapsed
                            or rid in coordinator.committed):
                        continue
                    review_lapsed.add(case)
                    await spine.emit_event(
                        "capacity.deadline_lapse", agent_id="coordination",
                        caused_by=round_ev,
                        payload={"case_id": case, "commitment_id": rid,
                                 "deadline_round": fuse, "round_no": round_no,
                                 "forced": False, "review": True})
                # Per-case fuse lapse: "respond by day D" means committed during
                # round <= D. A passed fuse is MARKED (capacity.deadline_lapse,
                # forced: false) but the case stays open — a disposal between the
                # fuse and the period plan scores late at half magnitude (delivery
                # rule v2.1's graded tier; the lateness DV must be able to rise
                # with density before outright failures do). The period plan
                # deadline is where undisposed cases are force-closed.
                for case, rounds in sorted(case_rounds.items()):
                    fuse = rounds.get("deadline")
                    did = disposition_id.get(case)
                    if (fuse is None or did is None or round_no <= fuse
                            or case in fuse_lapsed):
                        continue
                    if did in coordinator.committed:
                        continue
                    fuse_lapsed.add(case)
                    await spine.emit_event(
                        "capacity.deadline_lapse", agent_id="coordination",
                        caused_by=round_ev,
                        payload={"case_id": case, "commitment_id": did,
                                 "deadline_round": fuse, "round_no": round_no,
                                 "forced": False})
                # Plan-deadline forcing (deadline order): the plan's owed blockers
                # first — transitively, so an unfiled case's filings close before
                # its disposition — then the plan itself through carry_forward.
                async def _force_with_blockers(cid: str, caused_by: str) -> None:
                    for blocker in coordinator.contract.commitment(cid).blocks:
                        if blocker not in coordinator.committed:
                            await _force_with_blockers(blocker, caused_by)
                    await _force_slot(cid, caused_by, "deadline_lapse")
                for pid, deadline in plan_deadlines.items():
                    if round_no <= deadline or pid in coordinator.committed:
                        continue
                    lapse_ev = await spine.emit_event(
                        "capacity.deadline_lapse", agent_id="coordination",
                        caused_by=round_ev,
                        payload={"commitment_id": pid, "deadline_round": deadline,
                                 "round_no": round_no, "forced": True})
                    await _force_with_blockers(pid, lapse_ev)
                # Duty notice (apparatus constant, arm-identical): EVERY live role
                # gets the day notice each round, whether or not it is currently
                # admissible — a role unblocked mid-round must not act without the
                # current day and deadlines (audit 2026-08-15 P1-3: readiness-gated
                # delivery made timer awareness endogenous to organizational form).
                # Admission is readiness-gated, so delivery has no scheduling side
                # effects; items fold into the role's next turn.
                checkpoints = ", ".join(
                    f"{pid.replace('_', ' ')} by day {d}"
                    for pid, d in plan_deadlines.items())
                for role in org_spec.roles:
                    agent = rs.agents.get(role.role_id)
                    if agent is None or agent.retired:
                        continue
                    tc = tc_by_role[role.role_id]
                    due = slot_due.get(tc.submit_commitment_id)
                    duty = (f"Your current duty '{tc.submit_commitment_id}' is due "
                            f"by day {due}. " if due is not None else "")
                    await _deliver(MailboxItem(
                        item_id=new_ulid(), kind="clock_notice",
                        payload=clock_notice_text(round_no=round_no, rounds_total=rounds_total,
                                                  duty=duty, checkpoints=checkpoints),
                        source_event_id=round_ev,
                    ), role.role_id, rs)

            # Correspondence file (PI directive 2026-08-27; knee-grid forensic:
            # compaction dropped notice BODIES and repairs became ungroundable —
            # r12 dismissals cited "not retained in the compacted context
            # summary"). Every arrived packet is ALSO filed in the recipient's
            # private scratch, byte-identical to the envelope rendering
            # (model_agent's sort_keys/indent dump), so context loss becomes
            # recoverable at attention cost instead of absorbing. Recipients are
            # the attention-scope targets — office privacy rides the routing
            # unchanged. A write failure is run-fatal (fail closed).
            # The case file (outcomes/case_file.py; CH2 workload pilot, 2026-09-24):
            # every notice an agent receives is also registered under its case id,
            # so a slot that declares ``case_file`` can re-deliver, with its duty
            # notice, the records committed on the case and the notices THIS agent
            # already holds — recovery without a read tool, visibility unchanged.
            case_notices: dict[str, dict[str, list[dict]]] = {}
            # every notice released on a case, whoever received it: a decision's case file may
            # name a field of these to show its decider the case's alternatives (2026-10-04)
            case_released: dict[str, list[dict]] = {}

            # The central store (LK1 H-F, 2026-09-25): ONE role, named by the preset's
            # ``live_coordination.central_store``, holds a readable store in its own
            # scratch — an index, the declared standing materials split into sections
            # under the read tool's cap, and every notice as the clock releases it (a
            # notice from a later round does not exist in the store until its round).
            # Only a role granted read_file can read its scratch; no other role's
            # container mounts it. Reads are logged (file.read) and enter the request.
            _store_cfg = (org_spec.live_coordination or {}).get("central_store") or {}
            _store_role = _store_cfg.get("role")
            _store_dir = (rd.agent_scratch(_store_role) / "store") if _store_role else None
            _store_seen: set[str] = set()
            if _store_dir is not None:
                from oaos2.experiments.central_store import write_store_materials
                write_store_materials(_store_dir, pack, list(_store_cfg.get("materials") or []),
                                      notices=bool(_store_cfg.get("notices", True)))

            def _file_correspondence(*, agent_id: str, packet) -> None:
                folder = rd.agent_scratch(agent_id) / "correspondence"
                folder.mkdir(parents=True, exist_ok=True)
                day = packet.arrival_round or 0
                (folder / f"day{day:02d}_{packet.packet_id}.json").write_text(
                    json.dumps(packet.payload, sort_keys=True, indent=2))
                payload = packet.payload if isinstance(packet.payload, dict) else {}
                case_id = str(payload.get("case_id") or "").strip()
                if case_id:
                    case_notices.setdefault(agent_id, {}).setdefault(case_id, []).append(payload)
                    case_released.setdefault(case_id, []).append(payload)
                if _store_dir is not None and _store_cfg.get("notices", True) and packet.packet_id not in _store_seen:
                    from oaos2.experiments.central_store import file_released_notice
                    _store_seen.add(packet.packet_id)
                    file_released_notice(_store_dir, packet, recipient=agent_id)

            rs.environment_delivery_sink = _file_correspondence

            def _build_case_file(commitment_id: str, agent_id: str) -> str:
                from oaos2.outcomes.case_file import case_file_spec, render_case_file
                try:
                    commitment = coordinator.contract.commitment(commitment_id)
                except Exception:  # noqa: BLE001 — not a commitment id
                    return ""
                spec = case_file_spec(commitment)
                if not spec:
                    return ""
                ex = _clocked_impl.get("exchange")
                payloads = coordinator.payloads
                # A role that does not commit this slot (an office recovering the case it was
                # queried on, in a private fan-in arrangement) sees only records IT committed:
                # the counterpart's filing is not its information (audit 2026-09-25, P1).
                plays = set(next((r.plays for r in org_spec.roles if r.role_id == agent_id), ()))
                if not (plays & set(commitment.committer_roles)):
                    own = {cid for cid in coordinator.committed
                           if plays & set(coordinator.contract.commitment(cid).committer_roles)}
                    payloads = {cid: pl for cid, pl in coordinator.payloads.items() if cid in own}
                return render_case_file(spec, payloads=payloads,
                                        notices=case_notices.get(agent_id, {}),
                                        released=case_released.get(str(spec.get("case_id", "")), []),
                                        exchange_lines=(ex.lines_for(agent_id, str(spec.get("case_id", "")))
                                                        if ex is not None else None))

            rs.case_file_builder = _build_case_file
            for role in org_spec.roles:  # folder exists from day 1 (empty = no mail yet)
                (rd.agent_scratch(role.role_id) / "correspondence").mkdir(
                    parents=True, exist_ok=True)

            # The case exchange (plugins/budget_execution/exchange.py; LK1, 2026-09-25):
            # installed only when a role is granted one of its actions, so every
            # existing preset keeps its behaviour. Offices with a pending query are
            # admitted for a turn even when their duty is not ready, and may not
            # submit that duty during such a turn.
            _exchange_actions = {"send_query", "send_reply", "send_assent", "send_peer_note"}
            if any(_exchange_actions & set(r.tools or ()) for r in org_spec.roles):
                from oaos2.tasks.plugins.budget_execution.exchange import CaseExchange, assent_precheck
                _seq_by_role = {r.role_id: _role_commitment_seq(r) for r in org_spec.roles}
                _case_offices: dict[str, list[str]] = {}
                # the offices of a case are the committers of the records its disposition
                # waits on, read from the declared timing bindings, never from slot names
                for case, cid in bindings.disposition_id.items():
                    _records = set(bindings.case_filings.get(case, ())) | set(bindings.due_with_ids)
                    for blocker in coordinator.contract.commitment(cid).blocks:
                        if blocker not in _records:
                            continue
                        for rid, seq in _seq_by_role.items():
                            if blocker in seq and rid not in _case_offices.setdefault(case, []):
                                _case_offices[case].append(rid)
                _center_ids = {rid for rid, seq in _seq_by_role.items() if final_commitment_id in seq}
                # Later notices (context-shift schedules): which office each one reaches,
                # resolved by the same scope rule as delivery, and the review slot it opens.
                from oaos2.environment.driver import _scope_receives
                _updates = {}
                for case, u in sorted(update_rounds.items()):
                    _offices = [r.role_id for r in org_spec.roles
                                if _scope_receives(rs.environment_scopes.get(r.role_id, r.role_id),
                                                   tuple(u["target_scopes"]))]
                    _updates[case] = {"offices": _offices, "round": int(u["arrival"]),
                                      "packet_id": u["packet_id"],
                                      "review_slot": bindings.review_id.get(case),
                                      "first_slot": bindings.disposition_id.get(case)}
                exchange = CaseExchange(
                    case_offices=_case_offices, center_ids=_center_ids,
                    current_round=lambda: (rs.clock.round_no if rs.clock is not None else 0),
                    slot_case=dict(slot_case), updates=_updates,
                    payload_of=lambda cid: coordinator.payloads.get(cid))
                _clocked_impl["exchange"] = exchange
                _clocked_impl["slot_case"] = slot_case
                _assent_in_use = any("send_assent" in set(r.tools or ()) for r in org_spec.roles)
                for role in org_spec.roles:
                    tc = tc_by_role[role.role_id]
                    exchange.attach(tc)
                    tc.protocol_state["recoverable_slots"] = (
                        lambda rid=role.role_id: exchange.recoverable_slots(rid))
                    if _assent_in_use:
                        tc.submit_prechecks.append(assent_precheck)
                    if role.role_id in _center_ids:
                        tc.protocol_state["may_end_turn"] = (
                            lambda tc=tc, rid=role.role_id: exchange.may_end_turn(rid, tc.submit_commitment_id))
                        continue

                    def _query_gate(base, rid):
                        def gate():
                            return ((base is None or base()) or bool(exchange.pending_for(rid))
                                    or exchange.update_open_for(rid))
                        return gate

                    def _hold(base, rid):
                        # a role admitted while its own duty is not ready (only the pending
                        # query gate does that) may not submit the duty, and may end its turn
                        def hold():
                            if base is not None and not base():
                                if exchange.update_open_for(rid) and not exchange.pending_for(rid):
                                    return ("your current duty is not open now (its notices have not arrived, "
                                            "or you have no duty left); this turn was opened because a later "
                                            "notice reached you: you may file one update with send_update, or "
                                            "end your turn")
                                return ("your current duty is not open now (its notices have not arrived, "
                                        "or you have no duty left); this turn was opened for you to answer "
                                        "a query with send_reply, after which you may end your turn")
                            return None
                        return hold

                    _base = readiness_by_role.get(role.role_id)
                    _wrapped = _query_gate(_base, role.role_id)
                    readiness_by_role[role.role_id] = _wrapped
                    rs.readiness[role.role_id] = _wrapped
                    _hold_fn = _hold(_base, role.role_id)
                    tc.protocol_state["submission_hold"] = _hold_fn
                    tc.protocol_state["may_end_turn"] = (
                        lambda tc=tc, rid=role.role_id, hold=_hold_fn: exchange.may_end_turn(
                            rid, tc.submit_commitment_id, hold_active=bool(hold())))

            rs.clock = ClockState(rounds_total=rounds_total, on_round=_on_round)
            # the filings each case's disposition waits on, as the contract stood when the run
            # was made — so a readout's readiness never depends on the repository's current
            # profile (build audit 2026-09-25)
            _case_filings = {}
            for case, cid in bindings.disposition_id.items():
                try:
                    blocks = list(coordinator.contract.commitment(cid).blocks)
                except Exception:  # noqa: BLE001
                    blocks = []
                _records = set(bindings.case_filings.get(case, ())) | set(bindings.due_with_ids)
                _case_filings[case] = sorted(b for b in blocks if b in _records)
            manifest.extensions["clock"] = {
                **pack.clock.to_manifest(),
                "case_rounds": {c: dict(r) for c, r in sorted(case_rounds.items())},
                "case_filings": dict(sorted(_case_filings.items())),
                # later notices and the review slots they open (context-shift schedules; {} otherwise)
                "update_rounds": {c: dict(u, review=bindings.review_id.get(c)) for c, u in sorted(update_rounds.items())},
                # the daily call ceiling each role actually ran under (role override or the clock's)
                "calls_per_role": {r.role_id: (r.calls_per_day or pack.clock.calls_per_day) for r in org_spec.roles}}
            manifest.write(rd.manifest_path)

        # The form's platform orchestration (deliberation, hierarchy report
        # watchdog + draft review, …) is the protocol's — run beside the agent
        # loops by run_supervisor(on_start=...); None for forms without one.
        on_start = protocol.make_on_start(ctx)
    except BaseException as _setup_exc:  # noqa: BLE001 — abort re-raises
        await session.abort(_setup_exc)

    run_error: BaseException | None = None
    isolation_error: BaseException | None = None
    session.begin_execution()
    try:
        # Overall deadlock backstop: if an upstream role retires WITHOUT committing its
        # blocker (e.g. cost-capped before submitting), a downstream role would wait
        # forever on readiness. Bound the whole supervisor generously (cost is the real
        # stopper); a legit live run finishes well inside this.
        supervisor_timeout = max(wall_clock_cap, 1800) * (org_spec.n_agents + 1)
        await asyncio.wait_for(
            run_supervisor(rs, on_start=on_start),
            timeout=supervisor_timeout)
        # Clock wind-down (live solo w7 post-mortem, 2026-08-15): when every
        # agent has retired (e.g. cost-capped) with the outcome still open,
        # the runtime exits mid-clock and the schedule strands. The platform
        # winds the clock forward itself — remaining arrivals dispatch, lapsed
        # fuses are marked, and the plan-deadline forcing closes the books —
        # so a dead organization still yields a complete, scoreable archive.
        if rs.clock is not None and not coordinator.closed:
            wind_from = rs.clock.round_no
            while not coordinator.closed and await rs.clock.advance():
                pass
            if rs.clock.round_no > wind_from:
                await spine.emit_event(
                    "clock.wind_down", agent_id="coordination",
                    payload={"from_round": wind_from,
                             "to_round": rs.clock.round_no,
                             "reason": "runtime ended with the outcome open "
                                       "(agents retired/cost-capped); platform "
                                       "wound the clock out"})
    except asyncio.TimeoutError:
        await spine.emit_event("run.deadlock_timeout", payload={"timeout_s": supervisor_timeout})
    except BaseException as exc:  # incl. ExceptionGroup carrying an IsolationViolation
        # Present an exhausted submission gate as its domain exception rather than an
        # asyncio TaskGroup wrapper. Other run-fatal groups (notably isolation breaches)
        # retain their existing group semantics for callers that inspect group members.
        run_error = _nested_exception(exc, CommitmentConformanceError) or exc
    finally:
        if stop_watch is not None and not stop_watch.done():
            stop_watch.cancel()
        session.begin_winddown()
        # Completeness backstop (M4 §3): surface any disk change with no matching
        # capture (or vice-versa) before teardown erases the bind mount.
        # Platform-written StateCommitment payloads are explained writes
        # (audit 2026-09-03) — registered per COMMITTED id only, so a stray
        # file in submitted/ still flags.
        for _cid in coordinator.committed:
            wm.record_platform_write(coordinator.submitted_dir / f"{_cid}.json")
        try:
            await wm.reconcile([rd.container_mount])
        except Exception:  # noqa: BLE001 — reconcile is a backstop, never a hard stop
            pass
        # A symlink escape at capture is run-fatal (isolation.py contract:
        # "violations fail the run") — teardown_all surfaces it, and never
        # lets an ordinary capture failure mask the run result.
        isolation_error = await session.teardown_all(
            "failure" if run_error is not None else "success")
    if run_error is None:
        run_error = isolation_error
    if run_error is None:
        run_error = next((tc.submit_conformance_failure for tc in tool_ctxs
                          if tc.submit_conformance_failure is not None), None)
    if run_error is not None:
        await session.abort(run_error, teardown=False)  # containers already down

    # Post-execution seal (audit round 7 P1-2): scoring, environment
    # verification, labeling, finalize, and status persistence abort through
    # the session too — a populated trace can never end without a terminal
    # record. (abort() skips finalize when 'completed' already landed.)
    try:
        score = await _score(pack, coordinator, spine, tier=tier)
        if environment_driver is not None:
            environment_driver.assert_complete()
        if mode == "confirmatory" and not score["scored"]:
            await session.finalize("failed")
            _render_derived(rd.root)
            raise RuntimeError("confirmatory cell closed without a successful headline evaluation")
        label = label_outcome(rd.root, list(coordinator.committed_event_ids.values()))
        # Surface the realized exposure from the archive: if ANY model call ran with a
        # degraded exposure (a requested trace/visibility the backend couldn't produce
        # exactly), the cell is confounded (M3 §2.1). In confirmatory mode the gateway would
        # have refused upstream, so this is meaningful only in pilot/calibration.
        confounded = _exposure_confounded_from_archive(rd.root)
        # Realized-vs-declared binding certificate (C1h): every `model.invoked`
        # per role must carry the manifest's declared ref. A mismatch is an
        # APPARATUS fault — raised as a ConfoundViolation before the terminal
        # record so the cell finalizes 'failed' (abort below), never 'completed'.
        from oaos2.organizations.confound_check import certify_role_model_refs
        from oaos2.trace.invariants import load_all_events
        _events = load_all_events(rd.root)
        certify_role_model_refs(_events, role_model_refs)
        role_facts = _role_model_facts(_events)
        report = await session.finalize("completed")
        # HARD-ERROR CONTRACT (DESIGN §6.3, probe 2026-08-17): a non-ok invariant
        # report fails the cell loudly (see run_one; same rule on the live path).
        spine.raise_if_invalid()
        _render_derived(rd.root)  # re-render derived/ transcripts + metrics from the frozen archive

        partial = score.get("partial_score")  # headline evaluator's score (None if it has none)
        result = CellResult(
            preset_id=org_spec.preset_id, model_ref=model_ref, closed=coordinator.closed,
            passed=score["passed"], label=label, archive_valid=report.ok, scored=score["scored"],
            score_detail=score,
            n_agents=org_spec.n_agents, run_dir=rd.root, partial_score=partial,
            cost_usd=ledger.spent_usd, output_tokens=ledger.spent_output_tokens,
            difficulty=tier, context_budget=context_budget,
            pricing_table_version=table.version, pricing_table_hash=table.hash(),
            cache_policy_fingerprint=cache_fp, exposure_confounded=confounded,
            runtime="raw_api",  # the host-owned loop — true by construction (adapters are transport-only)
            parity_basis=parity_basis, parity_regime=parity_regime,
            rounds_total=(pack.clock.rounds_total if clocked else None),
            clock_label=clock_label,
            role_model_refs=role_model_refs,  # certified above
        )
        _persist_run_status(rd.root, result, **role_facts,
                            realized_reasoning_kind=manifest.extensions["realized_reasoning_kind"])
    except BaseException as _post_exc:  # noqa: BLE001 — abort re-raises
        await session.abort(_post_exc, teardown=False)  # containers already down
    return result


async def _score(pack: TaskPack, coordinator: OutcomeCoordinator, spine: RunSpine,
                 tier: str | None = None) -> dict:
    """Score committed milestones; the headline confirmatory result comes from the evaluator
    that self-declares it. ``tier`` is offered to evaluators that opt in (a ``tier`` kwarg in
    their signature): an ambiguity-manipulating pack must route its headline by the CELL's
    tier, not the submission's shape, so scoring is consistent across arms within a tier
    (an organic-arm LOW cell that echoes the agreed priority must not get graded on the
    equivocal rubric). Evaluators without the kwarg are called exactly as before."""
    import inspect
    detail: dict = {}
    passed = False
    partial = None  # the headline evaluator's partial_score, if it produces one
    headline_label = None  # the headline evaluator's own label, if it gives one
    evaluation_ok = True
    headline_required = any(getattr(ev, "produces_headline_score", False)
                            for ev in pack.evaluators.values())
    headline_completed = False
    feedback_schema = pack.feedback_schema()  # pack-declared schema id, not a hardcoded key
    for commitment in coordinator.contract.commitments:
        if commitment.commitment_id not in coordinator.payloads:
            continue
        payload = coordinator.payloads[commitment.commitment_id]
        for evaluator_ref in commitment.evaluators:
            evaluator = pack.evaluators.get(evaluator_ref)
            if evaluator is None:
                continue  # deferred (e.g. defensibility_rubric)
            # Per-evaluator hidden-ref hook (generic; no task name hardcoded): an evaluator that
            # needs its answer key host-side exposes input_ref().
            input_ref = evaluator.input_ref() if hasattr(evaluator, "input_ref") else None
            # A throwing/timing-out evaluator must NOT abort the run: the outcome is
            # left unscored and flagged via evaluation.failed (M6 §4/§6).
            try:
                sig_params = inspect.signature(evaluator.evaluate).parameters
                tier_kw = ({"tier": tier} if tier is not None and
                           "tier" in sig_params else {})
                # Cross-commitment visibility for evaluators that declare it —
                # the same optional channel conformance gates already have
                # (check_conformance's committed=). Named trigger: the C1
                # headline evaluator scores the JOINT outcome over all
                # committed choices, which no single slot payload carries.
                committed_kw = ({"committed": dict(coordinator.payloads)}
                                if "committed" in sig_params else {})
                raw = evaluator.evaluate(payload=payload, commitment=commitment,
                                         input_ref=input_ref, **tier_kw,
                                         **committed_kw)
            except Exception as exc:  # noqa: BLE001 — evaluator failure is recorded, not fatal
                evaluation_ok = False
                await spine.emit_event(
                    "evaluation.failed",
                    caused_by=coordinator.committed_event_ids.get(commitment.commitment_id),
                    payload={"commitment_id": commitment.commitment_id,
                             "evaluator_ref": evaluator_ref, "error": str(exc)},
                )
                detail[f"{commitment.commitment_id}:{evaluator_ref}"] = {"evaluation_failed": str(exc)}
                continue
            rec = write_evaluation(
                raw=raw, public_schema=feedback_schema,
                outcome_id=coordinator.contract.outcome_id, commitment_id=commitment.commitment_id,
            )
            await spine.emit_event(
                "evaluation.completed", caused_by=coordinator.committed_event_ids.get(commitment.commitment_id),
                payload={"commitment_id": commitment.commitment_id, "evaluator_ref": evaluator_ref,
                         "agent_feedback": rec.agent_feedback},
            )
            detail[f"{commitment.commitment_id}:{evaluator_ref}"] = rec.researcher_diagnostics
            # The headline pass/fail comes from the evaluator that self-declares it produces the
            # headline score (numeric_compare for paper_replication; budget_allocation.score) —
            # regardless of which commitment carries it. Generic; no evaluator name hardcoded.
            if getattr(evaluator, "produces_headline_score", False):
                headline_completed = True
                passed = bool(rec.researcher_diagnostics.get("passed"))
                partial = rec.researcher_diagnostics.get("partial_score")  # None if the scorer has none
                # the scorer's own one-line reading of its verdict, when it gives one (the
                # materials lab splits honest from violating credits); None otherwise
                headline_label = rec.researcher_diagnostics.get("label")
    scored = evaluation_ok and (headline_completed or not headline_required)
    return {"passed": passed, "partial_score": partial, "scored": scored,
            "evaluation_ok": evaluation_ok, "headline_completed": headline_completed,
            "headline_label": headline_label, "evaluations": detail}


@dataclass
class SweepResult:
    design_name: str
    mode: str
    results: list  # list[CellResult]
    results_by_preset: dict  # preset_id -> CellResult
    confound_ok: bool
    capacity_facts: dict | None
    headline: dict  # preset_id -> partial_score (or passed)
    confound_violation: str | None = None  # the specific violation when confound_ok is False
    intervention_facts: dict | None = None  # per-cell intervention rates + the recorded-rate gap (M7 §4)
    parity_facts: dict | None = None  # ex-ante regime + realized-compute (mediator) per arm, and the gap (M7 §4)
    results_by_factor: dict = field(default_factory=dict)  # factor-key -> replication cells
    headline_by_factor: dict = field(default_factory=dict)  # factor-key -> replication mean


def _resolved_sweep_plan(design, *, execution: str, replications: int,
                         cap_usd_override: float | None, cap_tokens_override: int | None,
                         max_concurrency: int, scheduled_cells: list[dict],
                         rep_indices: tuple | None = None,
                         replacement_of: str | None = None,
                         effort: str | None = None) -> dict:
    """Canonical post-override plan: the experiment that will actually be dispatched."""
    pp = design.parity_policy
    return {
        # Only when set, so plans launched without it keep their hashes.
        **({"launcher_effort": effort} if effort is not None else {}),
        "schema_version": 1,
        # Fault-replacement provenance (prereg replacement rule): a one-cell rerun
        # names the replication index it re-fills and the faulted run it replaces.
        "rep_indices": list(rep_indices) if rep_indices is not None else None,
        "replacement_of": replacement_of,
        "design_name": design.name,
        "design_source_ref": str(design.source_ref) if design.source_ref else None,
        "design_source_sha256": _sha256_file(design.source_ref),
        "task_pack": design.task_pack,
        "declared_mode": design.mode,
        "effective_cell_mode": design.mode if execution == "live" else "pilot",
        "execution": execution,
        # These are the in-memory factors after launcher narrowing/overrides — the source
        # YAML may declare a wider factorial and is separately hash-pinned above.
        "resolved_factors": {key: list(value) for key, value in sorted(design.factors.items())},
        "replications": replications,
        "platform_seed": design.platform_seed,
        "preregistration_ref": design.preregistration_ref,
        "parity_policy": {
            "basis": pp.basis,
            "regime": pp.regime,
            "design_cap_usd": pp.cap_usd,
            "design_cap_tokens": pp.cap_tokens,
            "final_reserve_tokens": pp.reserve_tokens,
            "launcher_cap_usd": cap_usd_override,
            "launcher_cap_tokens": cap_tokens_override,
        },
        "max_concurrency": max(1, max_concurrency) if execution == "live" else 1,
        "scheduled_cells": scheduled_cells,
    }


async def run_sweep(design, runs_root: Path, *, execution: str = "offline",
                    replications: int | None = None, cap_usd: float | None = None,
                    cap_tokens: int | None = None,
                    backend=None, adapter_factory=None,
                    max_concurrency: int = 1, on_result=None,
                    rep_indices: tuple | None = None,
                    replacement_of: str | None = None,
                    effort: str | None = None) -> SweepResult:
    """Run the design's factor combinations and return a SweepResult.

    Offline execution uses simulated agents and containers. Live execution uses
    configured providers and containers and needs separate launch authorization.
    max_concurrent_cells bounds simultaneous live cells; it is an operational
    setting, not an experimental factor. effort is the reasoning effort for cells whose
    models take one instead of a budget; other cells ignore it. on_result receives each
    completed live CellResult so the caller can persist progress. See the returned confound and
    capacity findings as well as individual scores."""
    from oaos2.organizations.confound_check import (
        ConfoundViolation, confound_check, single_agent_capacity_check)
    from oaos2.experiments.naming import experiment_dir_name, run_id
    from oaos2.organizations.presets import ALL_PRESETS

    design.validate()
    reps = replications if replications is not None else design.replications
    presets = design.factors.get("org_preset", list(ALL_PRESETS))
    if design.mode == "confirmatory":
        # Typed readiness preflight (audit round 8 P1-4): prereg FINAL +
        # declared capacity evidence + no deferred-protection arms — refused
        # BEFORE any cell exists, never discovered post-hoc. An OFFLINE
        # execution of a confirmatory design is a structural dry-run (its
        # cells are pilot cells, gated below as pilot) and must stay runnable
        # before the evidence exists — readiness gates the LIVE launch.
        from oaos2.experiments.confirmatory import assert_confirmatory_ready
        launch_orgs = [_resolve_org(p) for p in presets]
        assert_confirmatory_ready(
            org_specs=launch_orgs,
            preregistration_ref=design.preregistration_ref,
            evidence=design.confirmatory_evidence,
            require_evidence=False,
            block_deferred_arms=(execution == "live"),
            task_pack=design.task_pack,
            # REALIZED launch sets, mirroring the dispatcher's own defaults
            # (probe round 2: empty factors made the match vacuous while the
            # cells ran the defaults) — evidence must cover what actually runs:
            # the run-level factor UNION every preset's role-level refs (C1h).
            model_refs=_launch_model_refs(
                design.factors.get("model") or ("stub/deterministic",), launch_orgs),
            tiers=tuple(design.factors.get("difficulty") or ("hard",)))
    # The design's replication count is authoritative (from the manifest); callers may
    # override it (e.g. offline dry-runs use 1 for speed without spending money).
    difficulties = design.factors.get("difficulty") or ["hard"]
    model_refs = design.factors.get("model") or ["stub/deterministic"]
    # context_budget is a swept factor (the bounded-capacity IV); [None] = unbounded baseline.
    context_budgets = design.factors.get("context_budget", [None])
    # clock is a swept factor of per-cell ClockSpec overrides (repair item 4):
    # each entry is {"name": <legible label>, **ClockSpec._OVERRIDE_KEYS}. The
    # override is validated by ClockSpec.override at cell start; canonical pack
    # files are never touched. [None] = the pack's manifest clock (or batched).
    clock_variants = design.factors.get("clock") or [None]
    _clk_names = [c.get("name") if isinstance(c, dict) else None
                  for c in clock_variants if c is not None]
    if any(n is None for n in _clk_names) or len(set(_clk_names)) != len(_clk_names):
        raise ValueError("factors.clock entries must be dicts with unique 'name' labels")
    if any(c is not None for c in clock_variants):
        # Validate the whole factorial BEFORE any cell exists (audit round 5
        # P2-5): a clock factor against a batched preset would otherwise fail
        # (or worse, silently no-op) one cell at a time mid-sweep.
        _unclocked = [p for p in presets
                      if _resolve_org(p).scheduler != "clocked_rounds"]
        if _unclocked:
            raise ValueError(
                f"factors.clock requires clocked_rounds presets; batched: {_unclocked}")

    if execution not in ("offline", "live"):
        raise ValueError(f"unknown execution mode {execution!r}")
    if execution == "offline" and any(c is not None for c in clock_variants):
        raise ValueError(
            "clock factors run through execution='live' (with a stub "
            "adapter_factory + FakeContainerBackend for offline smoke) — "
            "run_one's offline path is batched-only")

    # Legible experiment_id + a UNIQUE, legible run_id per cell × replication
    # (encodes preset/difficulty/model/rep + a ULID), so each run is a distinct archive
    # and re-runs/replications never clobber (DESIGN §17.3).
    exp_id = experiment_dir_name(design.name)

    def _rid(preset_id: str, difficulty: str, model_ref: str, rep: int,
             clk: dict | None = None) -> str:
        return run_id(preset=preset_id, difficulty=difficulty, model_ref=model_ref,
                      rep=rep, variant=(clk or {}).get("name"))

    # Cell execution order is randomized under the design's platform_seed (M7 §4),
    # so any order-dependent confound (e.g. provider rate-limit drift over a sweep)
    # is shuffled deterministically across re-runs — reproducible, not fixed dict order.
    import random as _random

    # Expand the full declared factorial in one randomized schedule. Comparisons are
    # blocked by (difficulty, model, context budget) downstream, so tier/model effects
    # can never be silently confounded with separate invocation time.
    cells = [(difficulty, model_ref, preset_id, cb, clk, rep)
             for difficulty in difficulties for model_ref in model_refs
             for preset_id in presets for cb in context_budgets
             for clk in clock_variants
             for rep in (rep_indices if rep_indices is not None else range(reps))]
    _random.Random(design.platform_seed).shuffle(cells)

    live_cells = None
    if execution == "live":
        resolved_cap = (cap_usd if cap_usd is not None
                        else design.parity_policy.cap_usd if design.parity_policy.cap_usd is not None
                        else 3.0)
        from oaos2.pricing.ledger import validate_spending_cap
        resolved_cap = validate_spending_cap(resolved_cap, allow_unbounded=False)
        live_cells = [(rn, budget, difficulty, model_ref, p, cb, clk, rep)
                      for rn, budget in design.parity_policy.resolve_budgets(
                          base_cap_usd=resolved_cap, base_cap_tokens=cap_tokens)
                      for difficulty, model_ref, p, cb, clk, rep in cells]
        # Regime is a scheduled factor too. With ``both``, running every matched cell
        # before every unconstrained cell would confound regime with provider/time drift.
        _random.Random(design.platform_seed).shuffle(live_cells)
        scheduled = [{
            "schedule_index": index,
            "regime": regime,
            "budget": {
                "cap_usd": budget["cap_usd"],
                "cap_output_tokens": budget.get("cap_output_tokens"),
                "final_reserve_tokens": budget.get("final_reserve_tokens", 0),
            },
            "difficulty": difficulty,
            "model_ref": model_ref,
            "org_preset": preset,
            "context_budget": context_budget,
            "clock": clock,
            "replication_index": rep,
        } for index, (regime, budget, difficulty, model_ref, preset,
                      context_budget, clock, rep) in enumerate(live_cells)]
    else:
        scheduled = [{
            "schedule_index": index,
            "regime": "budget_matched",
            "budget": None,
            "difficulty": difficulty,
            "model_ref": model_ref,
            "org_preset": preset,
            "context_budget": context_budget,
            "clock": clock,
            "replication_index": rep,
        } for index, (difficulty, model_ref, preset, context_budget, clock,
                      rep) in enumerate(cells)]
    if execution == "live":
        from oaos2.pricing.ledger import validate_spending_cap
        for _, budget, *_ in live_cells:
            validate_spending_cap(budget["cap_usd"], allow_unbounded=False)
    if execution == "live" and design.mode == "confirmatory":
        from dataclasses import replace
        from oaos2.experiments.coordination import resolve_coordination_protocol
        from oaos2.experiments.confirmatory import ConfirmatoryReadinessError
        if not _source_state().get("source_code_sha256"):
            raise ConfirmatoryReadinessError("confirmatory execution requires readable executable-source identity")
        setups = set()
        for _, budget, difficulty, model, preset, cb, clk, _rep in live_cells:
            org = _resolve_org(preset)
            protocol = resolve_coordination_protocol(org)
            profile = (org.live_coordination or {}).get("contract_profile") or protocol.contract_profile
            if isinstance(profile, dict):
                profile = profile[difficulty]
            pack = load_task_pack(design.task_pack, decomposed=protocol.is_decomposed, profile=profile)
            if clk:
                pack = replace(pack, clock=pack.clock.override({k: v for k, v in clk.items() if k != "name"}))
            setups.add(_research_setup_sha(
                pack, org, tier=difficulty, model_ref=model, context_budget=cb,
                cap_usd=float(budget["cap_usd"]), cap_output_tokens=budget.get("cap_output_tokens"),
                final_reserve_tokens=budget.get("final_reserve_tokens", 0),
                parity_basis=design.parity_policy.basis,
                integrator_role=protocol.integrator_role(org, pack, _rep), effort=effort))
        assert_confirmatory_ready(
            org_specs=launch_orgs, preregistration_ref=design.preregistration_ref,
            evidence=design.confirmatory_evidence, task_pack=design.task_pack,
            model_refs=_launch_model_refs(model_refs, launch_orgs), tiers=tuple(difficulties),
            setup_sha256s=setups)
    resolved_sweep = _resolved_sweep_plan(
        design, execution=execution, replications=reps,
        cap_usd_override=cap_usd, cap_tokens_override=cap_tokens,
        max_concurrency=max_concurrency, scheduled_cells=scheduled,
        rep_indices=rep_indices, replacement_of=replacement_of, effort=effort)

    results: list = []
    if execution == "offline":
        # Each arm runs the SAME contract profile offline as it does live (the same
        # protocol resolution run_org_live uses), so an arm is structurally identical
        # across modes — only the cognition (stub solver vs real model) differs. The
        # arms legitimately use different contracts (pipeline decomposed; the rest
        # single-submission); they remain comparable because the SCORED quantity is
        # numeric_compare on the final numbers either way (M7 §3).
        from oaos2.experiments.coordination import resolve_coordination_protocol
        _packs: dict[str, object] = {}
        for difficulty, model_ref, preset_id, cb, _clk, rep in cells:
            org = _resolve_org(preset_id)
            # Offline the stub solver commits the profile's milestones (no
            # deliberation); the structural gate is profile-faithful. Same
            # preset-pinned override live uses (the v2 amendment-round profiles).
            arm_protocol = resolve_coordination_protocol(org)
            dec = arm_protocol.is_decomposed
            profile = ((org.live_coordination or {}).get("contract_profile")
                       or arm_protocol.contract_profile
                       or ("decomposed" if dec else "single_results"))
            pack = _packs.get(profile) or _packs.setdefault(
                profile, load_task_pack(design.task_pack, decomposed=dec, profile=profile))
            r = await run_one(pack, org, runs_root,
                              run_id=_rid(preset_id, difficulty, model_ref, rep),
                              experiment_id=exp_id, mode="pilot", model_ref=model_ref,
                              tier=difficulty, preregistration_ref=design.preregistration_ref,
                              design_ref=design.source_ref,
                              resolved_sweep_plan=resolved_sweep)
            r.context_budget = cb  # offline: stamped only (stub solver accumulates no real context)
            r.parity_regime = "budget_matched"  # the dry-run counterpart of the live parity regime
            r.parity_basis = design.parity_policy.basis
            results.append(r)
    else:  # live — honor the ParityPolicy regimes (M7 §4): ex-ante usd cap per arm,
        # realized compute recorded (not conditioned on); run both regimes if declared.
        # Cells are independent (own RunDir/spine/backend/deepcopy'd contract), so they run
        # CONCURRENTLY under a bounded semaphore: the sweep's wall-clock becomes the slowest
        # ~max_concurrency window, not the sum. Determinism is untouched (per-cell archives
        # are independent; results are sorted before the comparison/gate below).
        sem = asyncio.Semaphore(max(1, max_concurrency))

        async def _live_cell(regime_name, regime_budget, difficulty, model_ref,
                             preset_id, cb, clk, rep):
            async with sem:
                org = _resolve_org(preset_id)
                try:
                    r = await _dispatch_live_cell(
                        org, regime_name, regime_budget, difficulty, model_ref,
                        preset_id, cb, clk, rep)
                except Exception as exc:  # noqa: BLE001 — calibration records, never aborts
                    # A run-fatal cell (e.g. retry-exhausted conformance death) is
                    # CALIBRATION EVIDENCE, not a sweep abort: record a failed row and
                    # let the remaining cells run (mode=calibration is exploratory by
                    # declaration). Pilot/confirmatory keep the fail-closed re-raise —
                    # there a dead cell invalidates the comparison (2026-08-12 round 1:
                    # one dead vertical cell silently cost the whole sweep table).
                    if design.mode != "calibration":
                        raise
                    r = CellResult(
                        preset_id=preset_id, model_ref=model_ref, closed=False,
                        passed=False, label="assisted", archive_valid=False,
                        scored=False,
                        score_detail={"run_failed": f"{type(exc).__name__}: {exc}"},
                        n_agents=org.n_agents, difficulty=difficulty,
                        context_budget=cb, runtime="raw_api",
                        parity_regime=regime_name,
                        parity_basis=design.parity_policy.basis,
                        rounds_total=(clk or {}).get("rounds_total"),
                        clock_label=(clk or {}).get("name"),
                        role_model_refs=_role_model_refs(org, model_ref))
                if on_result is not None:
                    on_result(r)
                return r

        async def _dispatch_live_cell(org, regime_name, regime_budget, difficulty,
                                      model_ref, preset_id, cb, clk, rep):
            return await run_org_live(
                org, runs_root, tier=difficulty,
                run_id=_rid(preset_id, difficulty, model_ref, rep, clk),
                model_ref=model_ref, experiment_id=exp_id, mode=design.mode,
                cap_usd=regime_budget["cap_usd"],
                cap_output_tokens=regime_budget["cap_output_tokens"],
                final_reserve_tokens=regime_budget.get("final_reserve_tokens", 0),
                parity_basis=design.parity_policy.basis,
                parity_regime=regime_name,
                task_pack=design.task_pack, preregistration_ref=design.preregistration_ref,
                confirmatory_evidence=design.confirmatory_evidence,  # per-cell backstop input
                design_ref=design.source_ref,
                resolved_sweep_plan=resolved_sweep,
                context_budget=cb, integrator_rotation=rep,  # D9: composer rotates by replication
                effort=effort,  # run-wide, like the cap; budget-model cells ignore it
                backend=backend, adapter_factory=adapter_factory,
                # Strip the schedule label; the rest is a validated ClockSpec override.
                clock_override=({k: v for k, v in clk.items() if k != "name"}
                                if clk else None),
                clock_label=(clk or {}).get("name"),
            )

        tasks = [_live_cell(*cell) for cell in live_cells]
        # return_exceptions=True so one failing cell does NOT cancel its in-flight siblings
        # (which would orphan their containers); we still fail-closed by re-raising the first
        # cell exception AFTER every sibling has finished cleanly.
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for g in gathered:
            if isinstance(g, BaseException):
                raise g
        results = list(gathered)

    # The headline, per-preset map, confound gate, and capacity check are all the
    # cross-arm COMPARISON, which must be made within ONE parity basis — the
    # budget_matched regime (M7 §4). With regime="both" each cell ran twice; keying
    # `by_preset` off all results would silently keep whichever regime iterated last
    # (the unconstrained 3x-cap run), comparing arms at a non-parity cap. So compare on
    # the budget_matched subset; `parity_facts` still reports BOTH regimes + the gap.
    primary = [r for r in results if getattr(r, "parity_regime", "budget_matched") == "budget_matched"]
    if not primary:  # a budget_matched-free design (regime="unconstrained") — compare what ran
        primary = results
    # Preserve every replication. The compatibility view returns a CellResult only
    # when a preset has exactly one primary cell; otherwise its value is the complete
    # list, making ambiguity explicit rather than selecting an arbitrary replication.
    preset_groups: dict[str, list] = {}
    factor_groups: dict[tuple, list] = {}
    for r in primary:
        preset_groups.setdefault(r.preset_id, []).append(r)
        # clock_label in the key: distinct clock factors (horizon AND
        # burstiness) are distinct factor cells — arms are only ever compared
        # within one temporal condition (audit round 5 P1-1).
        key = (r.difficulty, r.model_ref, r.context_budget, r.clock_label)
        factor_groups.setdefault(key, []).append(r)
    by_preset = {pid: cells[0] if len(cells) == 1 else cells
                 for pid, cells in preset_groups.items()}
    confound_ok = True
    confound_violation = None
    intervention_facts: dict = {}
    # An offline execution of a confirmatory design is a structural DRY-RUN: its cells
    # are pilot cells (run_one stamps runtime="offline_stub"), so gate them as pilot —
    # only a live confirmatory sweep faces (and aborts on) the confirmatory gates.
    gate_mode = design.mode if execution == "live" else "pilot"
    violations: list[str] = []
    capacity_by_factor: dict = {}
    for key, compared in sorted(factor_groups.items(), key=lambda item: str(item[0])):
        key_text = (f"difficulty={key[0]}|model={key[1]}|context={key[2]}"
                    + (f"|clock={key[3]}" if key[3] is not None else ""))
        try:
            intervention_facts[key_text] = confound_check(compared, mode=gate_mode)
        except ConfoundViolation as exc:
            confound_ok = False
            violations.append(f"{key_text}: {exc}")
            if gate_mode == "confirmatory":
                raise
        grouped = {pid: [r for r in compared if r.preset_id == pid]
                   for pid in {r.preset_id for r in compared}}
        if {"single_agent", "context_expanded_single_agent"} <= set(grouped):
            try:
                capacity_by_factor[key_text] = single_agent_capacity_check(grouped)
            except ConfoundViolation as exc:
                capacity_by_factor[key_text] = {"premise_holds": False, "error": str(exc)}
                if gate_mode == "confirmatory":
                    raise
    confound_violation = "; ".join(violations) if violations else None
    if len(capacity_by_factor) == 1:
        capacity_facts = next(iter(capacity_by_factor.values()))
    else:
        capacity_facts = capacity_by_factor or None

    headline_by_factor, headline = _headline_facts(primary)
    return SweepResult(
        design_name=design.name, mode=design.mode, results=results, results_by_preset=by_preset,
        confound_ok=confound_ok, capacity_facts=capacity_facts,
        headline=headline,
        confound_violation=confound_violation,
        intervention_facts=intervention_facts or None,
        parity_facts=_parity_facts(results),
        results_by_factor={str(key): value for key, value in factor_groups.items()},
        headline_by_factor=headline_by_factor,
    )


def _headline_facts(primary: list) -> tuple[dict, dict]:
    """Headline means within exact factor blocks — (headline_by_factor, headline).

    A named function so the grouping is testable in isolation (audit round 7
    P2-5: budget_execution scores archive-side and never exercises this path
    in the sweep property tests). The factor key carries clock_label: distinct
    temporal conditions never average together. Missing evaluations are
    omitted (and already fail the confound gate); they are never zeroed.
    """
    factor_scores: dict[tuple, list[float]] = {}
    for r in primary:
        value = (float(r.partial_score) if r.partial_score is not None
                 else float(bool(r.passed)) if r.scored else None)
        if value is not None:
            factor_scores.setdefault(
                (r.preset_id, r.difficulty, r.model_ref, r.context_budget,
                 r.clock_label), []).append(value)
    headline_by_factor = {key: sum(values) / len(values)
                          for key, values in factor_scores.items()}
    comparison_levels = {(r.difficulty, r.model_ref, r.context_budget, r.clock_label)
                         for r in primary}
    headline = ({key[0]: value for key, value in headline_by_factor.items()}
                if len(comparison_levels) == 1 else {
                    f"{key[0]}|difficulty={key[1]}|model={key[2]}|context={key[3]}"
                    + (f"|clock={key[4]}" if key[4] is not None else ""): value
                    for key, value in headline_by_factor.items()
                })
    return headline_by_factor, headline


def _parity_facts(results: list) -> dict:
    """Ex-ante parity regime + realized resource use (descriptive, not an abort gate;
    M7 §4 / §19). Reports per-arm realized usd within each regime, the cross-arm realized-
    compute gap, and — when both regimes ran — whether the arm ranking by score is stable
    across them (the gap-report the design asks for). These summaries do not establish
    that resource use causally mediates an organizational effect."""
    by_regime: dict = {}
    for r in results:
        reg = getattr(r, "parity_regime", "budget_matched")
        cell_key = (r.preset_id, r.difficulty, r.model_ref, r.context_budget,
                    getattr(r, "clock_label", None))
        regime = by_regime.setdefault(reg, {"by_factor": {}, "by_preset": {}})
        for collection, key in ((regime["by_factor"], cell_key),
                                (regime["by_preset"], r.preset_id)):
            slot = collection.setdefault(key, {"cost": [], "tokens": [], "partial": []})
            slot["cost"].append(float(r.cost_usd or 0.0))
            slot["tokens"].append(float(r.output_tokens or 0))
            if r.partial_score is not None:
                slot["partial"].append(float(r.partial_score))
            elif r.scored:
                slot["partial"].append(float(bool(r.passed)))

    def _mean(xs): return sum(xs) / len(xs) if xs else 0.0
    bases = {getattr(r, "parity_basis", "usd") for r in results}
    facts: dict = {"basis": next(iter(bases)) if len(bases) == 1 else "mixed",
                   "by_regime": {}}
    def _summarize(slots):
        return {str(p): {"mean_realized_usd": round(_mean(v["cost"]), 4),
                         "mean_realized_output_tokens": round(_mean(v["tokens"]), 2),
                         "mean_partial": (round(_mean(v["partial"]), 4)
                                          if v["partial"] else None),
                         "n": len(v["cost"]), "n_scored": len(v["partial"])}
                for p, v in slots.items()}

    for reg, groups in by_regime.items():
        summ = _summarize(groups["by_preset"])
        by_factor = _summarize(groups["by_factor"])
        costs = [s["mean_realized_usd"] for s in summ.values()]
        tokens = [s["mean_realized_output_tokens"] for s in summ.values()]
        facts["by_regime"][reg] = {"by_preset": summ,
                                   "by_factor": by_factor,
                                   "realized_cost_gap": round(max(costs) - min(costs), 4) if costs else 0.0,
                                   "realized_output_token_gap": round(max(tokens) - min(tokens), 2)
                                   if tokens else 0.0}
    regimes = list(facts["by_regime"])
    if len(regimes) > 1:  # the cross-regime stability the gap-report hinges on
        def _rank(reg):
            # Compare like-for-like cells across regimes; the aggregate by-preset view
            # remains for backwards-compatible reporting and arm-level summaries.
            scored = facts["by_regime"][reg]["by_factor"]
            return tuple(sorted((p for p in scored if scored[p]["mean_partial"] is not None),
                                key=lambda p: scored[p]["mean_partial"]))
        facts["ordering_stable_across_regimes"] = len({_rank(reg) for reg in regimes}) == 1
    return facts


def _write_config_snapshot(rd, config: dict) -> None:
    """Write the resolved run configuration (DESIGN §17.3) to ``config/resolved.json``."""
    (rd.config / "resolved.json").write_text(json.dumps(config, indent=2, sort_keys=True))
