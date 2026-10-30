"""Load task materials, submission contracts, and scoring registrations.

Read library/tasks/<pack>/manifest.yaml, resolve the selected contract profile,
verify declared hidden-reference hashes, and build the TaskPack used by the
runner. A contract profile selects submissions and their dependencies. Plugins
supply task-specific behavior; configuration selects the implemented options."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from oaos2.evaluation.public_feedback import PublicFeedbackSchema
from oaos2.library import library_dir
from oaos2.outcomes.contracts import ClosureCondition, Commitment, OutcomeContract
from oaos2.tasks.clock import ClockSpec
from oaos2.tasks.pack import RolePacket, TaskPack
from oaos2.tasks.registry import build_evaluator


class ManifestError(Exception):
    """A malformed task-pack manifest, or a hidden-reference hash mismatch."""


def _resolve_trace_vocabulary(m: dict, pack_id: str):
    """Manifest ``trace_vocabulary`` → resolved registries composed over the
    foundation vocabularies (M0 §5.2 ``inherits_from`` — the config-as-data path
    for pack event classes / phase names / comm kinds). The foundation tables are
    never edited: the pack layer composes over them and the runner injects the
    RESOLVED registries into ``RunSpine``/``Router``. Fail-closed: an unknown
    section, an invalid phase/audience/channel value, an unknown comm primitive,
    or a collision with a foundation name refuses the load."""
    tv = m.get("trace_vocabulary") or {}
    if not tv:
        return None, None, None
    unknown = set(tv) - {"event_classes", "phase_names", "comm_kinds"}
    if unknown:
        raise ManifestError(
            f"pack {pack_id!r} trace_vocabulary has unknown sections "
            f"{sorted(unknown)} (allowed: event_classes, phase_names, comm_kinds)")
    from oaos2.communication.messages import COMM_KIND_SPEC, COMM_PRIMITIVES
    from oaos2.registry import RegistryError, RegistrySpec
    from oaos2.trace.event_classes import EVENT_CLASS_SPEC, PHASE_NAME_SPEC, EventClassDef
    from oaos2.trace.schema import Audience, Channel, PhaseClass

    phase_classes = {p.value for p in PhaseClass}
    audiences = {a.value for a in Audience}
    channels = {c.value for c in Channel}

    event_entries = {}
    for name, decl in (tv.get("event_classes") or {}).items():
        decl = dict(decl or {})
        missing = {"phase_class", "audience", "channel"} - set(decl)
        if missing:
            raise ManifestError(
                f"pack {pack_id!r} event class {name!r} is missing {sorted(missing)}")
        for field_name, allowed in (("phase_class", phase_classes),
                                    ("audience", audiences), ("channel", channels)):
            if decl[field_name] not in allowed:
                raise ManifestError(
                    f"pack {pack_id!r} event class {name!r}: {field_name} "
                    f"{decl[field_name]!r} not in {sorted(allowed)}")
        event_entries[name] = EventClassDef(
            decl["phase_class"], decl["audience"], decl["channel"],
            str(decl.get("emitted_by", pack_id)))

    phase_entries = {}
    for name, phase_class in (tv.get("phase_names") or {}).items():
        if phase_class not in phase_classes:
            raise ManifestError(
                f"pack {pack_id!r} phase name {name!r}: phase_class "
                f"{phase_class!r} not in {sorted(phase_classes)}")
        phase_entries[name] = phase_class

    kind_entries = {}
    for kind, primitive in (tv.get("comm_kinds") or {}).items():
        if primitive not in COMM_PRIMITIVES:
            raise ManifestError(
                f"pack {pack_id!r} comm kind {kind!r}: primitive {primitive!r} "
                f"not in {sorted(COMM_PRIMITIVES)}")
        kind_entries[kind] = primitive

    def _compose(section, parent_spec, entries):
        if not entries:
            return None
        try:
            return RegistrySpec(registry_id=f"{pack_id}.{section}", entries=entries,
                                inherits_from=(parent_spec,)).resolve()
        except RegistryError as exc:  # foundation-name collision — never shadow silently
            raise ManifestError(
                f"pack {pack_id!r} trace_vocabulary.{section}: {exc}") from exc

    return (_compose("event_classes", EVENT_CLASS_SPEC, event_entries),
            _compose("phase_names", PHASE_NAME_SPEC, phase_entries),
            _compose("comm_kinds", COMM_KIND_SPEC, kind_entries))


def _pack_dir(pack_id: str) -> Path:
    return library_dir() / "tasks" / pack_id  # resolved at call time (honors OAOS2_LIBRARY)


def load_manifest(pack_id: str) -> dict:
    path = _pack_dir(pack_id) / "manifest.yaml"
    if not path.is_file():
        raise ManifestError(f"no manifest for pack {pack_id!r} at {path}")
    return yaml.safe_load(path.read_text())


def _verify_hidden_refs(pack_dir: Path, hidden_refs: dict) -> list[str]:
    """Hash-verify every present hidden ref; a missing REQUIRED ref fails closed.

    Returns the ids of declared-but-missing OPTIONAL refs — a silent scoring
    degradation (e.g. a dropped multi-path best-of variant) that the caller records on
    the run so the absence is on the face of the archive, not invisible (M7 §2.2).
    """
    missing_optional: list[str] = []
    for ref_id, spec in hidden_refs.items():
        p = pack_dir / spec["path"]
        if not p.is_file():
            if spec.get("required", False):
                raise ManifestError(f"hidden ref {ref_id!r} missing at {p}")
            missing_optional.append(ref_id)
            continue
        actual = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != spec["sha256"]:
            raise ManifestError(f"hidden ref {ref_id!r} hash mismatch: expected {spec['sha256']}, got {actual}")
    return missing_optional


def _routing(c: dict, stage_registry: list | None) -> dict:
    """Stage-routing metadata, validated at load (audit rounds 6 P2-3, 7 P2-3).

    The loader validates generic SHAPE only — stage vocabulary is the PACK's
    (open-registry rule: validated, never enumerated in core): a manifest
    that uses routing declares its stages under ``routing_stages``. Office is
    REQUIRED and non-blank — the runner builds timeout stand-ins from it.
    """
    routing = dict(c.get("routing", {}))
    if not routing:
        return routing
    unknown = set(routing) - {"stage", "office"}
    if unknown:
        raise ManifestError(
            f"commitment {c['id']!r} routing: unknown keys {sorted(unknown)}")
    if stage_registry is None:
        raise ManifestError(
            f"commitment {c['id']!r} declares routing but the manifest "
            f"declares no routing_stages registry")
    # Registry SHAPE is validated too (audit round 8 P2-5): a bare string
    # ("routing_stages: report") would pass membership by SUBSTRING; a
    # registry is a nonempty unique sequence of nonblank strings.
    # Element types are checked BEFORE the uniqueness set() (probe 2026-08-17):
    # an unhashable entry must get this typed error, not a raw TypeError.
    if (isinstance(stage_registry, str) or not isinstance(stage_registry, (list, tuple))
            or not stage_registry
            or not all(isinstance(s, str) and s.strip() for s in stage_registry)
            or len(set(stage_registry)) != len(stage_registry)):
        raise ManifestError(
            "routing_stages must be a nonempty list of unique nonblank "
            f"strings, got {stage_registry!r}")
    if routing.get("stage") not in stage_registry:
        raise ManifestError(
            f"commitment {c['id']!r} routing.stage {routing.get('stage')!r} "
            f"not in the manifest's routing_stages {sorted(stage_registry)}")
    office = routing.get("office")
    if not (isinstance(office, str) and office.strip()):
        raise ManifestError(
            f"commitment {c['id']!r} routing.office must be a non-blank string")
    return routing


def _build_contract(pack_id: str, task_id: str, profile: dict,
                    stage_registry: list | None = None) -> OutcomeContract:
    commitments = [
        Commitment(
            commitment_id=c["id"],
            kind=c.get("kind", "artifact_submission"),
            required=c.get("required", True),
            committer_roles=list(c.get("committer_roles", [])),
            evaluators=[c["evaluator"]] if c.get("evaluator") else [],
            blocks=list(c.get("blocks", [])),
            submission=dict(c.get("submission", {})),  # submit-time shape gate + retry policy
            timing=dict(c.get("timing", {})),  # clocked-time metadata (tasks/clock.py schema)
            routing=_routing(c, stage_registry),  # stage-routing metadata (validated above)
        )
        for c in profile["commitments"]
    ]
    contract = OutcomeContract(
        outcome_id=f"{pack_id}_{task_id}",
        commitments=commitments,
        closure_condition=ClosureCondition(kind=profile.get("closure", "all_required_committed")),
    )
    contract.validate()
    return contract


from oaos2.tasks.actions import build_actions


def _prompt_apparatus(m: dict) -> tuple[str, dict]:
    """Validate the manifest's opening-message layout and built-in tool description overrides.

    Both are apparatus text a pack declares once for every role and arm; an unknown layout
    or an override for a tool that is not built in fails the load rather than reaching a run."""
    from oaos2.agents.tools import BUILTIN_TOOL_NAMES
    layout = str(m.get("prompt_layout", "analysis"))
    if layout not in ("analysis", "duties", "lab", "workshop"):
        raise ValueError(f"pack {m.get('pack_id')!r}: prompt_layout must be 'analysis', 'duties', 'lab' or "
                         f"'workshop', not {layout!r}")
    overrides = dict(m.get("tool_descriptions") or {})
    bad = sorted(set(overrides) - BUILTIN_TOOL_NAMES)
    if bad:
        raise ValueError(f"pack {m.get('pack_id')!r}: tool_descriptions names non-built-in tools {bad}")
    for name, text in overrides.items():
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"pack {m.get('pack_id')!r}: tool_descriptions[{name!r}] must be non-empty text")
    return layout, {k: " ".join(v.split()) for k, v in overrides.items()}


def load_task_pack(pack_id: str, *, decomposed: bool = True, profile: str | None = None) -> TaskPack:
    """Load a task pack from its manifest (the canonical source of truth).

    `profile` selects the contract profile explicitly (e.g. "deliberated"); when None it
    derives from `decomposed` ("decomposed" | "single_results")."""
    m = load_manifest(pack_id)
    pack_dir = _pack_dir(pack_id)
    assets = pack_dir / "assets"
    missing_optional_refs = _verify_hidden_refs(pack_dir, m.get("hidden_refs", {}))  # fail closed on tamper

    # Task-owned submission gates (audit round 8 P1-2): the manifest names its
    # gate modules; importing registers them with outcomes/conformance's open
    # registry. Config-declared — core enumerates no task gate vocabulary.
    import importlib
    for mod in (m.get("submission_gates") or []):
        try:
            importlib.import_module(str(mod))
        except Exception as exc:  # noqa: BLE001 — a missing gate module is fail-closed
            raise ManifestError(
                f"submission_gates module {mod!r} failed to import: {exc}") from exc

    # Task-owned evaluator plugins, same pattern: the manifest names modules whose
    # import registers evaluator ids with tasks/registry's open registry — a new
    # scoring family is a plugin module + this manifest line, never a core edit.
    for mod in (m.get("evaluator_modules") or []):
        try:
            importlib.import_module(str(mod))
        except Exception as exc:  # noqa: BLE001 — a missing evaluator module is fail-closed
            raise ManifestError(
                f"evaluator_modules module {mod!r} failed to import: {exc}") from exc

    # Submission-format keys fail at LOAD, not mid-run (probe round 2,
    # 2026-08-17): every key in every profile's `submission` blocks must be a
    # foundation key or a gate registered by THIS manifest's own declared
    # `submission_gates` modules — a typo'd or borrowed gate key must never
    # burn a live cell before anyone notices nothing enforces it.
    from oaos2.outcomes.conformance import _FOUNDATION_FMT_KEYS, gate_kinds_registered_by
    own_gate_kinds = gate_kinds_registered_by(m.get("submission_gates") or [])
    for profile_name_, profile_def in (m.get("contracts") or {}).items():
        for c in (profile_def.get("commitments") or []):
            unknown_keys = (set(c.get("submission") or {})
                            - _FOUNDATION_FMT_KEYS - own_gate_kinds)
            if unknown_keys:
                raise ManifestError(
                    f"pack {pack_id!r} profile {profile_name_!r} commitment "
                    f"{c.get('id')!r}: submission keys {sorted(unknown_keys)} are "
                    "neither foundation keys nor gates registered by this "
                    "manifest's declared submission_gates modules "
                    f"({sorted(own_gate_kinds) or 'none'}) — nothing would "
                    "enforce them")

    # Evaluators may name one of the manifest's hidden refs as ``input_ref``.  Resolve
    # that ref here so plugin code remains task-local and receives a verified host path
    # without hard-coding a library location or duplicating the digest.
    evaluators = {}
    declared_evaluator_modules = {str(mod) for mod in (m.get("evaluator_modules") or [])}
    for ref, declared_spec in m.get("evaluators", {}).items():
        # PROVENANCE, not presence (probe round 2, 2026-08-17): a non-foundation
        # id must have been registered BY a module this manifest itself declares
        # — declaring an unrelated module (or riding another pack's earlier
        # import) is refused. Provenance is the registering builder's module,
        # recorded at registration, so repeated loads stay valid.
        from oaos2.tasks.registry import EVALUATOR_PROVENANCE, FOUNDATION_EVALUATORS
        if (ref not in FOUNDATION_EVALUATORS
                and EVALUATOR_PROVENANCE.get(ref) not in declared_evaluator_modules):
            raise ManifestError(
                f"evaluator {ref!r} is not a foundation id and is not registered "
                f"by any module this manifest declares in `evaluator_modules:` "
                f"(declared: {sorted(declared_evaluator_modules) or 'none'}; "
                f"registered by: {EVALUATOR_PROVENANCE.get(ref, 'nothing')!r}) — "
                "process-global registrations from other packs' loads are not a "
                "declaration")
        spec = dict(declared_spec or {})
        input_ref_id = spec.get("input_ref")
        if input_ref_id is not None:
            try:
                hidden = m.get("hidden_refs", {})[input_ref_id]
            except KeyError:
                raise ManifestError(
                    f"evaluator {ref!r} names unknown hidden input_ref {input_ref_id!r}"
                ) from None
            spec["resolved_input_ref"] = {
                "ref": str(pack_dir / hidden["path"]),
                "content_hash": hidden["sha256"],
            }
        evaluators[ref] = build_evaluator(ref, spec)

    environment = dict(m.get("environment", {}) or {})
    if environment:
        resolved_schedules = {}
        for tier, ref_id in (environment.get("schedules", {}) or {}).items():
            try:
                hidden = m.get("hidden_refs", {})[ref_id]
            except KeyError:
                raise ManifestError(
                    f"environment schedule for {tier!r} names unknown hidden ref {ref_id!r}"
                ) from None
            resolved_schedules[tier] = {
                "ref": str(pack_dir / hidden["path"]),
                "content_hash": hidden["sha256"],
                "ref_id": ref_id,
            }
        environment["schedules"] = resolved_schedules
        # Stamped-schedule variants (per-cell horizon sweeps, repair item 4):
        # each variant is its own hash-pinned hidden asset, resolved exactly
        # like the canonical schedule — never a runtime mutation of it.
        resolved_variants = {}
        for variant, tiers in (environment.get("schedule_variants", {}) or {}).items():
            resolved_variants[variant] = {}
            for tier, ref_id in (tiers or {}).items():
                try:
                    hidden = m.get("hidden_refs", {})[ref_id]
                except KeyError:
                    raise ManifestError(
                        f"schedule variant {variant!r}/{tier!r} names unknown "
                        f"hidden ref {ref_id!r}") from None
                resolved_variants[variant][tier] = {
                    "ref": str(pack_dir / hidden["path"]),
                    "content_hash": hidden["sha256"],
                    "ref_id": ref_id,
                }
        environment["schedule_variants"] = resolved_variants

    fb = m.get("public_feedback", {})
    feedback = PublicFeedbackSchema(
        allowed_fields=frozenset(fb.get("allowed_fields", [])),
        forbidden_substrings=frozenset(fb.get("forbidden_substrings", [])),
    )

    contracts = m.get("contracts", {})
    profile_name = profile or ("decomposed" if decomposed else "single_results")
    if profile_name not in contracts:
        raise ManifestError(
            f"pack {pack_id!r} has no {profile_name!r} contract profile "
            f"(declared: {sorted(contracts)})"
        )
    contract = _build_contract(pack_id, m["task_id"], contracts[profile_name],
                           stage_registry=m.get("routing_stages"))

    role_packets = {}
    prompts = m.get("prompts", {})
    for role, fname in prompts.items():
        role_packets[role] = RolePacket(role, (assets / "prompts" / fname).read_text(errors="replace"), "all")

    # The live single-submission commitment: prefer the single_results profile, else fall
    # back to the chosen profile's final commitment — so a manifest with only one profile
    # still loads (a new pack is just a manifest, no code).
    if "single_results" in contracts:
        single_commitment = contracts["single_results"]["commitments"][0].get("id")
    else:
        # Decomposed-only manifest: bind live submit to the SCORED commitment (the one
        # carrying an evaluator), not the chain's last commitment — the tail is often an
        # optional, unscored review artifact. Fall back to the first commitment.
        cmts = contracts[profile_name]["commitments"]
        scored = next((c for c in cmts if c.get("evaluator")), cmts[0] if cmts else {})
        single_commitment = scored.get("id")
    if not single_commitment:
        raise ValueError(f"pack {m['pack_id']!r}: could not resolve a live submit commitment id")
    event_class_registry, phase_name_registry, comm_kind_registry = (
        _resolve_trace_vocabulary(m, pack_id))
    prompt_layout, tool_descriptions = _prompt_apparatus(m)
    from oaos2.docker.mounts import OMITTABLE
    omit = tuple(str(x) for x in (m.get("container_mounts_omit") or []))
    if set(omit) - OMITTABLE:
        raise ValueError(f"pack {pack_id!r}: container_mounts_omit may name only {sorted(OMITTABLE)}, not {omit}")
    return TaskPack(
        pack_id=m["pack_id"],
        zones=dict(m.get("zones", {})),
        role_packets=role_packets,
        outcome_contract=contract,
        public_feedback_schemas={fb.get("schema_id", "default"): feedback},
        evaluators=evaluators,
        task_dimensions=dict(m.get("task_dimensions", {})),
        hidden_refs=dict(m.get("hidden_refs", {})),
        science_image=m.get("science_image", ""),
        visible_dir=assets / "visible",
        hidden_dir=assets / "hidden",
        data_dir=pack_dir / m.get("data_dir", "assets/visible/data"),  # relative to pack dir
        prompts_dir=assets / "prompts",
        tier_materials=dict(m.get("visible_materials", {})),
        attention_materials=dict(m.get("attention_materials", {})),
        attention_output_spec=dict(m.get("attention_output_spec", {})),
        prompt_role=next(iter(prompts), "replicator"),
        required_output_ref=m.get("required_output_source"),
        prompt_layout=prompt_layout,
        tool_descriptions=tool_descriptions,
        container_mounts_omit=omit,
        live_submit_commitment=single_commitment,
        feedback_schema_id=fb.get("schema_id", "default"),
        missing_optional_refs=missing_optional_refs,
        deliberation_instruction=m.get("deliberation_instruction"),
        compaction_instruction=m.get("compaction_instruction"),
        inbox_heading=(str(m["inbox_heading"]).strip() or None) if m.get("inbox_heading") else None,
        # who keeps records.csv in the lab layout's note: the laboratory, or the workshop in the workshop layout,
        # unless the manifest names a keeper
        records_keeper=str(m.get("records_keeper")
                           or ("the workshop" if prompt_layout == "workshop" else "the laboratory")),
        compaction_max_tokens=m.get("compaction_max_tokens"),
        compaction_max_chars=m.get("compaction_max_chars"),
        ratification_instruction=m.get("ratification_instruction"),
        manifest_path=pack_dir / "manifest.yaml",
        contract_profile=profile_name,
        environment=environment,
        staged_coordination=dict(m.get("staged_coordination", {}) or {}),
        clock=ClockSpec.from_manifest(m.get("clock")),  # typed + validated at load
        event_class_registry=event_class_registry,
        phase_name_registry=phase_name_registry,
        comm_kind_registry=comm_kind_registry,
        offline_solver=m.get("offline_solver"),
        actions=build_actions(pack_id, m.get("actions")),
        repair_spec=dict(m.get("repair", {}) or {}),
    )
