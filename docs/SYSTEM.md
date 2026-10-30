# How the platform works

This page maps the code: how a run goes from a preset and a task pack to an archive, and which
package does each part. Paths are relative to the repository root. The [README](../README.md) gives
the quickstart, [WORLD.md](WORLD.md) explains the materials workshop, [ARCHITECTURE.md](ARCHITECTURE.md)
gives the reasons for the design, the [runbook](RUNBOOK.md) holds the commands, and the
[known limits](mechanism/DEFERRED.md) list what does not yet work as one might expect.

## 1. From a preset to an archive

A run has two inputs from `library/`: an organization **preset** (a YAML file in
`library/organizations/` that names the roles, their tools and permissions, the scheduler and the
task's settings) and a **task pack** (a folder in `library/tasks/` whose `manifest.yaml` declares the
actions agents may take, the texts each role receives and the evaluator that scores the work). A
launcher such as `scripts/run_materials_lab_smoke.py` or `examples/quickstart.py` passes both to
`run_org_live` in `oaos2/experiments/runner.py`.

**Loading and checking the settings.** `oaos2/organizations/loader.py` reads the preset and builds an
`OrganizationSpec` (`oaos2/organizations/spec.py`). `OrganizationSpec.validate` checks that roles,
channels and decision rights refer to one another correctly and that no role is granted more than the
organization allows. If the preset's `live_coordination.protocol_module` names a module that defines
`validate_settings(spec)`, `validate` calls it; the workshop's check
(`oaos2/tasks/plugins/materials_lab/settings.py`) refuses, by name, a setting it does not read and a
combination it would read and then ignore. The check runs when the preset loads and again when the run
starts. `oaos2/tasks/loader.py` resolves the task pack: its role texts, declared actions, contract
profile (which decisions the run must produce) and evaluator.

**Presets written on a base.** A preset may name another as its base (`base: <preset>`) and list only
what it changes (`read_preset` in `oaos2/organizations/loader.py`). Mappings merge key by key; any other
value, such as a list, a number or a text, replaces the base's whole value, so an overlay can set or
replace a setting but not remove one. An overlay must give its own `preset_id`. A preset marked
`base_only: true` is a base for others; loading it to run is refused. Bases can chain; a missing base is
refused, and so is a base that names the preset itself or an earlier preset in the chain. `org_path` looks for a preset in
`library/organizations/` first, then in the folders that the environment variable
`OAOS2_ORGANIZATIONS` names (this is how the tests find `tests/fixtures/organizations/`).
`scripts/compare_presets.py <a> <b> --check` lists, before any run, every setting in which two
presets differ with their bases applied. [WORLD.md](WORLD.md) shows how a study is written this way.

**Running the agents.** `RunSession` (`oaos2/experiments/session.py`) enforces the order: checks
before any resource is attached, then containers, then execution, then wind-down and closing. The
runtime (`oaos2/kernel/runtime.py`) runs each agent as an independent task; the preset's scheduler
(`oaos2/organizations/scheduler.py`) decides which ready agents may act, and the task's coordination
procedure (for the workshop, `oaos2/tasks/plugins/materials_lab/protocol.py`) runs beside the agent
loops, delivering results and messages into each agent's next turn.

**The agent loop.** The platform owns the loop rather than handing it to a provider's agent library.
`oaos2/agents/model_agent.py` assembles each model request from the role's texts, its conversation so
far and the tools it may use, sends it, and dispatches the tool calls in the reply. Before any tool runs,
`oaos2/agents/tools.py` checks that the role's grant names it, that file paths stay inside the areas the
role may read or write, and that a submission comes from a role entitled to make it. Task actions, such
as registering a prototype or filing a report in the workshop, are declared in the pack's manifest and
resolved to handlers by `oaos2/tasks/actions.py`; they are checked like built-in tools. A refused call
is recorded, not dropped. When a conversation grows past the role's context budget, the loop summarizes
or shortens it and records that as a `context.compaction` event. `oaos2/agents/capacity.py` enforces
the number of calls each agent may make.

**The model gateway and adapters.** Every model call goes through `call_model_gateway`
(`oaos2/models/gateway.py`). An **adapter** is the small module that translates a request into one
provider's format and the reply back. The adapters in `oaos2/models/adapters/` are registered by the
prefix of a model reference:

| Prefix | Adapter | Provider |
|---|---|---|
| `anthropic/` | `anthropic.py` | Anthropic |
| `openai/` | `openai.py` | OpenAI, Chat Completions |
| `openai_responses/` | `openai_responses.py` | OpenAI, Responses API (returns reasoning summaries) |
| `together/`, `openrouter/`, `opencode/` | `openai_compatible.py` | OpenAI-compatible hosts for open-weight models |
| `stub/` | `stub.py` | Simulated replies, for offline runs |

Keys are read on the host, never inside a container. The client libraries' own retries are turned off;
each adapter resends under one shared policy (`invoke_under_policy` in `base.py`), and every resend is
recorded as a `model.transport_retry` event. An OpenRouter reference may pin the serving hosts after
`@` (as in `openrouter/z-ai/glm-5.3-flash@z-ai`), so that a run is served the same way throughout.

**Spending.** One `CostLedger` per run (`oaos2/pricing/ledger.py`) holds a dollar cap and, optionally,
an output-token cap. Before each call the ledger reserves its projected cost; the call is refused if
completed spending plus all open reservations would exceed the cap. Afterwards the reservation is
settled from the usage the provider reports, priced by the table in `oaos2/pricing/table.py`. A call
whose usage stays unknown keeps its reservation and blocks further calls. Live runs require a positive,
finite cap.

**Containers.** Agents' code runs in Docker containers (`oaos2/docker/`) with network access disabled
by default; model calls come from the host, so the containers need none. Workspaces are host folders
mounted into the containers, so captured work survives a container failure. Hidden scoring materials
are never mounted. Offline runs use `FakeContainerBackend` (`oaos2/docker/backend.py`), which
simulates the containers without any isolation.

**The event record.** Every model call and reply, tool call, message, notice, accepted decision and
failure becomes an event, recorded through `RunSpine` (`oaos2/trace/spine.py`). One writer per run
(`oaos2/trace/writer.py`) appends the events and gives each a `sequence_number`, the only reliable
order (timestamps are not). Each event also carries `caused_by_event_ids`: the earlier events that
caused it, so a submission can be traced back to the messages and measurements behind it. Events wait
in a durable queue (`oaos2/trace/spool.py`) until written, so an interrupted run can be recovered. At
the end, `oaos2/trace/invariants.py` checks that the sequence has no gaps, that every cause precedes
its effect, and that the record ends properly.

## 2. What an archive contains

Each run is a folder `runs/<experiment>/<task pack>/<run id>/` (`oaos2/kernel/run_dir.py`):

| Path | Contents |
|---|---|
| `manifest.json` | What the run was: see below |
| `trace/events.jsonl`, `trace/infra.jsonl` | The event record, one JSON event per line; the authoritative evidence |
| `trace/index.sqlite` | A search index, rebuildable from the record |
| `raw/` | The providers' responses as returned, stored by content hash and cited from events |
| `config/` | The resolved configuration and each role's prompt envelope |
| `visible/`, `container_mount/`, `captured/`, `filesystem/` | Materials the agents could read, their workspaces and submissions, copies taken at cleanup, and file-change history |
| `derived/` | Transcripts, `metrics.json` and the task's report (for the workshop, `materials_lab_report.json`) |
| `run_status.json` | A summary: archive check, cost by role, outcome |
| `annotations/` | Researchers' labels, kept apart from the record |

`manifest.json` pins what is needed to identify the run. Its top level names the run, experiment,
task pack, organization, mode, container image and digest, the hash of the container policy, and the
price table. Its `extensions` hold content hashes (sha256) of the task manifest, the preset and, for an
overlay, each base it rests on (`organization_bases`), the role texts, the visible materials, the
hidden scoring references and the evaluator's source; the model assigned to each role; the caps; the
code's identity (`source_code_sha256`, a hash of the Python sources and dependency files, plus the Git
commit and whether the checkout had uncommitted changes); and a fingerprint of the whole research
setup.

**Derived readers.** Everything in `derived/` and every dashboard view is rebuilt from the record, not
kept as a second account. `render_archive` (`oaos2/archive/export.py`) writes the transcripts and
metrics and calls the task's registered report renderer; the [runbook](RUNBOOK.md) shows how to rerun it
on a saved run. The same record and the same reader code give the same output; changed reader code may
change a report, and the dashboard says when it shows a report computed by the current code rather
than the one saved with the run.

## 3. Where responsibilities live

| Package | Responsibility |
|---|---|
| `oaos2/organizations/` | Load and check presets (`loader.py`, `spec.py`), compare them (`compare.py`), schedulers, channels, the rule that a narrower scope may restrict but never widen a grant (`precedence.py`) |
| `oaos2/tasks/` | Load task packs (`loader.py`, `pack.py`), declared actions (`actions.py`), evaluator registry (`registry.py`), shared settings checks (`settings.py`); task plug-ins under `plugins/` |
| `oaos2/experiments/` | The runner (`runner.py`), run phases (`session.py`), clean stops (`stop.py`), coordination procedures (`coordination/`), experiment designs and pre-run checks |
| `oaos2/kernel/` | The concurrent runtime, run folders, manifest, logical clock |
| `oaos2/agents/` | The model agent loop, tool checks, call limits |
| `oaos2/models/` | Gateway, adapters, retained raw responses (`raw_store.py`), checks of what a model exposes (`exposure.py`) |
| `oaos2/pricing/` | Price table, cost attribution, the spending ledger |
| `oaos2/docker/`, `oaos2/workspace/` | Container policy and backends; workspace areas, file access, file history |
| `oaos2/communication/` | Messages, mailboxes, the board and notes, conversations |
| `oaos2/outcomes/`, `oaos2/evaluation/` | Accepting submissions (`commit.py` is the only writer of an accepted decision), checking their form, scorer interfaces |
| `oaos2/environment/` | Scheduled notices to the roles entitled to them |
| `oaos2/trace/` | Event schema and vocabulary, writer, queue, index, final checks |
| `oaos2/archive/` | Transcripts, datasets, citations, run index, readers the dashboard uses |
| `oaos2/annotations/` | Researchers' labels and codebooks |
| `oaos2/dashboard/` | The local dashboard ([guide](DASHBOARD.md)) |

The materials workshop's own code is in `oaos2/tasks/plugins/materials_lab/`; [WORLD.md](WORLD.md)
lists its parts.

## 4. How to add a capability

Choose the smallest change that does the job:

| Need | Where |
|---|---|
| A study on the workshop | Presets in `library/organizations/` that name `materials_workshop` as their base ([WORLD.md](WORLD.md), [example](../examples/new_study/README.md)) |
| A new setting the workshop reads | The plug-in's code and its list in `settings.py`, which refuses the setting otherwise |
| A new world | A task pack under `library/tasks/<name>/` and a plug-in under `oaos2/tasks/plugins/<name>/` |
| A new provider | An adapter in `oaos2/models/adapters/`, registered in its `__init__.py`, and price rows in `oaos2/pricing/table.py` |
| New event names for a task | The pack manifest's `trace_vocabulary` |
| A report or dashboard view for a task | The plug-in's `derived.py`, which registers its report renderer, exchange reader and work view |

A new world needs a manifest naming its actions, role texts and evaluator; a coordination procedure
that the preset names as `live_coordination.protocol_module` and that registers itself when imported;
a `validate_settings(spec)` function in that module that refuses settings the world does not read; and
readers for its records. A world adds registered implementations; the engine names no task, and adding
one should leave the engine's code unchanged. If a study needs something no existing interface can
express, specify the general interface first and record it in the [known limits](mechanism/DEFERRED.md).

Offline checks (simulated models and containers) test the machinery, not how real models behave. The
test suite's layout and the commands are in the [runbook](RUNBOOK.md).
