"""Define the task information passed from the loader to the runner.

TaskPack groups materials, host-only scoring references, role prompts,
submission contracts, feedback rules, evaluator registrations, and task
conditions. library/tasks/<pack>/manifest.yaml declares these inputs; the loader
resolves them and verifies supported references. A new task can use the existing
interfaces, while a new shared capability still needs implementation and checks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from oaos2.evaluation.public_feedback import PublicFeedbackSchema
from oaos2.outcomes.contracts import OutcomeContract
from oaos2.tasks.clock import ClockSpec


@dataclass
class RolePacket:
    role_id: str
    instructions: str
    attention_scope: str  # e.g. "sample/spec", "implementation", "review", "all"


@dataclass
class TaskPack:
    pack_id: str
    zones: dict[str, str]  # zone name → ZoneClass value (M4 §1)
    role_packets: dict[str, RolePacket]
    outcome_contract: OutcomeContract
    public_feedback_schemas: dict[str, PublicFeedbackSchema]
    evaluators: dict[str, object]  # evaluator_ref → evaluator plugin
    task_dimensions: dict = field(default_factory=dict)
    hidden_refs: dict = field(default_factory=dict)  # ref_id → {path, sha256, required}

    # Resolved asset locations + manifest-driven config (set by the loader).
    science_image: str = ""
    visible_dir: Path | None = None
    hidden_dir: Path | None = None
    data_dir: Path | None = None
    prompts_dir: Path | None = None
    tier_materials: dict = field(default_factory=dict)  # tier → [filenames]
    attention_materials: dict = field(default_factory=dict)  # attention scope → 'full'|'none'|[files]
    attention_output_spec: dict = field(default_factory=dict)  # attention scope → bool (inject the template?)
    prompt_role: str = "replicator"  # which role packet seeds the live system prompt
    required_output_ref: str | None = None  # hidden-ref id whose names/descriptions are public
    prompt_layout: str = "analysis"  # manifest `prompt_layout`: how the opening user message is laid
                                     # out. "analysis" is the original layout (required-output
                                     # template + sandbox notes). "duties" is for packs whose work
                                     # is a sequence of platform-announced duties: no empty
                                     # output template, and a submitting note written for several
                                     # submissions (realism review 2026-09-25, defect 3).
    tool_descriptions: dict = field(default_factory=dict)  # manifest `tool_descriptions`: built-in tool
                                                           # name -> the description this pack's roles
                                                           # see, replacing the generic analysis-task
                                                           # text (realism review 2026-09-25, defect 1)
    container_mounts_omit: tuple = ()  # manifest `container_mounts_omit`: read-only mounts left out of
                                       # every role's container (docker/mounts.py OMITTABLE)
    live_submit_commitment: str = "results"
    feedback_schema_id: str = "default"  # manifest public_feedback.schema_id (keys the schema dict)
    missing_optional_refs: list = field(default_factory=list)  # declared optional hidden refs absent at load
    deliberation_instruction: str | None = None  # pack-declared in-conversation instruction for the
                                                 # organic arm (None = the apparatus default constant
                                                 # in model_agent). Config-over-code: what counts as
                                                 # substantive deliberation is task-specific
                                                 # (revision doc D6), held constant across tiers.
    inbox_heading: str | None = None  # manifest `inbox_heading`: the heading over messages delivered
                                      # mid-conversation (None = the platform's "# Upstream handoff (cont.)")
    # manifest `records_keeper`: who keeps `records.csv`, in the lab layout's note on the working
    # directory (PC1 supplier-k, October 10, 2026: "the firm" for the testing firms).
    records_keeper: str = "the laboratory"
    compaction_instruction: str | None = None  # pack-declared summarizer prompt for context
                                               # compaction (None = the apparatus default in
                                               # model_agent); what a recap must keep is task-specific
    # manifest `compaction_max_chars` (October 12, 2026): a recap longer than this is cut at a paragraph boundary
    # before it is installed (None = no limit). A recap's requested length is an instruction; this enforces it.
    compaction_max_chars: int | None = None
    compaction_max_tokens: int | None = None  # pack-declared recap output ceiling (None = 2048)
    ratification_instruction: str | None = None  # pack-declared volley instruction for the draft-
                                                 # ratification round (revision doc D9): how a
                                                 # participant reacts to a circulated draft. Held
                                                 # constant across arms/tiers like the above.
    manifest_path: Path | None = None  # canonical source file, for run provenance
    contract_profile: str | None = None  # resolved profile name, for run provenance
    # Optional task-generic staged environment and automatic commitment-stage policy.
    # Hidden schedule refs are resolved and hash-pinned by the loader.
    environment: dict = field(default_factory=dict)
    staged_coordination: dict = field(default_factory=dict)
    # Clocked-rounds pack config: a typed, load-validated ClockSpec
    # (oaos2/tasks/clock.py owns every temporal invariant). None = batched-only
    # pack; the runner refuses a clocked run without it.
    clock: "ClockSpec | None" = None
    # Pack-composed trace vocabularies (M0 §5.2, manifest `trace_vocabulary`):
    # RESOLVED registries composed over the foundation specs via inherits_from.
    # The runner injects them into RunSpine/Router construction; None = the
    # foundation registry. A pack never edits the foundation tables.
    event_class_registry: object | None = None
    phase_name_registry: object | None = None
    comm_kind_registry: object | None = None
    # Manifest-declared offline stub solver module (probe 2026-08-17): imported
    # FAIL-CLOSED by the runner; None = the plugins/<pack_id>/solver convention.
    offline_solver: str | None = None
    # Registered task actions (M8 §2, manifest ``actions``): name -> TaskAction.
    # Offered to a role only when its tool grant names the action.
    actions: dict = field(default_factory=dict)
    # Pool configuration for repair-style packs (manifest ``repair``): issues,
    # bounds, grader settings. Read by the pack's own procedure; the engine
    # never interprets it.
    repair_spec: dict = field(default_factory=dict)

    def feedback_schema(self):
        """The pack's declared public-feedback schema (the diagnostic-split whitelist).

        Looked up by the manifest-declared id so the scorer is pack-agnostic — not bound
        to any one pack's schema key.
        """
        schemas = self.public_feedback_schemas
        if self.feedback_schema_id in schemas:
            return schemas[self.feedback_schema_id]
        if schemas:
            return next(iter(schemas.values()))  # single-schema packs: take the only one
        # A structure-only / minimal pack may declare no public-feedback schema. Degrade to
        # an empty whitelist (everything denied to agents) rather than crashing the scorer.
        from oaos2.evaluation.public_feedback import PublicFeedbackSchema
        return PublicFeedbackSchema(allowed_fields=frozenset())

    # -- generic, manifest-driven helpers ---------------------------------- #

    def data_mount_source(self) -> Path:
        """The read-only data dir — mounted ro at /visible/data (not copied per run). A pack whose data dir is
        empty has none in a fresh checkout (git keeps no empty directories); it is created empty so the mount
        has a source (October 19, 2026)."""
        assert self.data_dir is not None
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir

    def required_output_spec(self) -> str:
        """Public output template: required result NAMES + descriptions (values stripped).

        Reads the declared ``required_output_ref`` hidden file; descriptions name
        tables/quantities and carry no answer values, so they are safe to show.
        """
        if not self.required_output_ref or self.hidden_dir is None:
            return ""
        spec = self.hidden_refs.get(self.required_output_ref, {})
        path = self.hidden_dir / Path(spec["path"]).name if spec else None
        if not path or not path.is_file():
            return ""
        data = json.loads(path.read_text())
        return "\n".join(f"- {r['name']}: {r.get('description', '')}" for r in data.get("results", []))

    def _materials_for_attention(self, tier: str, attention: str) -> list[str]:
        """The tier materials this attention scope is ENTITLED to (DESIGN §18.1, §8).

        Resolves the manifest's ``attention_materials`` policy: ``full`` = every tier
        file; ``none`` = no paper (the role works from its handoff + mounted data); a list
        = those specific files. An unlisted scope defaults to ``full`` (back-compat: a
        pack with no policy gives every role the full materials). This is the information
        PARTITION that makes a decomposition real, not just role instructions.
        """
        all_files = list(self.tier_materials[tier])
        policy = self.attention_materials.get(attention, "full")
        if policy == "full":
            return all_files
        if policy == "none":
            return []
        allowed = set(policy if isinstance(policy, (list, tuple)) else [policy])
        return [f for f in all_files if f in allowed]

    def build_initial_prompt(self, tier: str, role: str | None = None,
                             attention: str = "all", tools: list | None = None) -> tuple[str, str]:
        """Assemble (system_prompt, initial_user_text) for a live agent (M7 WS5).

        System = the role packet for ``role`` (defaults to the pack's ``prompt_role``).
        User = the tier materials the role's ``attention`` scope is ENTITLED to (the paper
        is partitioned per role — §18.1/§8; the data CSVs are mounted ro for every role
        regardless) + the public required-output spec + sandbox/tool instructions. No
        answer values appear. A role entitled to no paper (e.g. the pipeline builder)
        gets a note that its inputs are the upstream handoff + the data.
        """
        if tier not in self.tier_materials:
            raise ValueError(f"unknown difficulty tier {tier!r} (have {sorted(self.tier_materials)})")
        assert self.visible_dir is not None
        packet_role = role or self.prompt_role
        if packet_role not in self.role_packets:
            raise ValueError(f"no role packet {packet_role!r} (have {sorted(self.role_packets)})")
        system_prompt = self.role_packets[packet_role].instructions

        entitled = self._materials_for_attention(tier, attention)
        if entitled:
            materials = "\n\n".join((self.visible_dir / n).read_text(errors="replace") for n in entitled)
            # A task's workshop layout avoids the word "materials" in its cover story (October 10, 2026).
            heading = "# Brief" if self.prompt_layout == "workshop" else "# Task materials"
            materials_section = f"{heading}\n\n{materials}\n\n"
        else:
            # Partitioned out of the paper (e.g. the builder): inputs are the handoff + data.
            materials_section = ("# Task materials\n\n"
                                 "Your inputs are the upstream handoff (provided to you) and the "
                                 "read-only data; you do not have the paper itself.\n\n")
        # Required-output template injection is Condition-A/B gated per attention scope
        # (the old platform's injection-vs-communication manipulation). Communication
        # roles (e.g. the pipeline builder) get no template — they learn what to compute
        # from the upstream handoff, which is the whole point of the decomposition.
        if self.prompt_layout in ("lab", "workshop"):
            # Lab layout (PC1 realism review, 2026-09-25, defect 1): the pack's own materials and
            # a note on the working directory, nothing else. The analysis layout told every
            # materials lab to compute "the results specified in the upstream handoff" and to
            # load `/visible/data/otree_individual_data.csv`; there is no handoff and no data,
            # and oTree is software for behavioral experiments.
            toolset = set(tools) if tools is not None else set()
            lines = ["# Your working directory"]
            if "run_python" in toolset:
                lines.append(f"- `run_python` runs Python 3 in your working directory, where {self.records_keeper} keeps "
                             "`records.csv` and where files you write are kept.")
            elif "read_file" in toolset:
                lines.append("- `read_file` reads files in your working directory, including `records.csv`.")
            return system_prompt, f"{materials_section}" + ("\n".join(lines) + "\n" if len(lines) > 1 else "")
        spec_text = self.required_output_spec()
        if self.prompt_layout == "duties" and not spec_text:
            # A duties pack has no result template; its shapes come with each duty notice.
            # The analysis layout would print an empty list under a heading here.
            outputs_section = ""
        elif self.attention_output_spec.get(attention, True):
            outputs_section = (
                "# Required outputs\n"
                "Submit a value for every result below (use these exact names as JSON keys):\n"
                f"{spec_text}\n\n"
            )
        else:
            outputs_section = (
                "# Required outputs\n"
                "The set of results you must produce is specified in the upstream handoff "
                "provided to you — compute and submit exactly those.\n\n"
            )
        # Sandbox/tool instructions describe ONLY the tools this role actually has
        # (tools=None → the full default set). A read-only role must not be told to use
        # run_python it doesn't have (which is both confusing and a tool it can't call).
        toolset = set(tools) if tools is not None else {"run_python", "read_file", "write_file", "submit_results"}
        if self.prompt_layout == "duties":
            # Duties layout: the roles hold no sandbox and submit several times; the analysis
            # wording ("call submit_results ONCE", "Your sandbox") contradicted their packets.
            lines = ["# Submitting"]
            if "submit_results" in toolset:
                lines.append("- Each duty is met by calling `submit_results` with the JSON payload its duty "
                             "notice states, one duty per call. When it commits, your next duty is announced.")
            if "read_file" in toolset:
                lines.append("- `read_file` reads the records your instructions describe, by the path they give.")
            user_text = f"{materials_section}{outputs_section}" + "\n".join(lines) + "\n"
            return system_prompt, user_text
        lines = ["# Your sandbox"]
        if "run_python" in toolset:
            lines.append("- The data CSVs are read-only at `/visible/data/` (e.g. "
                         "`/visible/data/otree_individual_data.csv`). Load them with pandas inside `run_python`.")
            lines.append("- Use the `run_python` tool to write and execute analysis code; print the numbers you need.")
        elif "read_file" in toolset:
            lines.append("- You have NO code execution. Use `read_file` to inspect files, including the "
                         "read-only data at `/visible/data/` (e.g. `/visible/data/otree_individual_data.csv`) "
                         "to see their columns/structure.")
        if "submit_results" in toolset:
            lines.append("- When done, call `submit_results` ONCE with a JSON object (the required "
                         "result_name -> value mapping, or the structured deliverable your role owns). "
                         "That commits your contribution.")
        user_text = f"{materials_section}{outputs_section}" + "\n".join(lines) + "\n"
        return system_prompt, user_text
