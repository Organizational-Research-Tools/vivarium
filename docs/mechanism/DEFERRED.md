# Known limits

This page lists what in this release does not work as a user might expect: settings that are
accepted but change nothing, code that names parts of the project not released here, and what the
offline checks and the cost controls do not establish. The [system map](../SYSTEM.md) describes how
the platform works; [WORLD.md](../WORLD.md) lists what is not yet standard in the materials workshop.

## Settings accepted without effect

The workshop's settings check refuses a setting it does not read and some combinations it would
ignore. A few settings are still read and recorded but have no effect in the competition study's base,
`materials_workshop.yaml`; [world/SETTINGS.md](../world/SETTINGS.md) notes each case:

- `density` is overridden by `difficulty_ladder` for every product line the ladder covers, and the
  base's ladder covers all three. The value still appears in the staging event and the run summary.
- `instance_seed` is replaced by the launcher's `--seed` on every run of
  `scripts/run_materials_lab_smoke.py`. The preset's value matters only to code that loads the preset
  without that launcher.
- `audit` draws its lottery only on the ordinary acceptance path. In the contest form, which the base
  uses, no report is ever audited; a probability above zero only routes concerns to the portal's log.

One accepted value needs a part that is not released. `vocabulary: testing` (allowed only with
`presentation: settings`) rewords the laboratories' texts for a variant in which the laboratories are
testing firms, and the launcher then loads that variant's task pack, `pc1_testing`. That pack is not in
this release, so such a run stops when the pack is loaded.

## Code that names parts not released

The platform was developed on earlier tasks and studies whose plug-ins are not in this release. Some
of their names remain:

- **An import in the runner.** `oaos2/experiments/runner.py` imports
  `oaos2.tasks.plugins.budget_execution.exchange` when any role of a preset is granted one of the
  actions `send_query`, `send_reply`, `send_assent` or `send_peer_note`. No released preset grants
  them; a new preset that does fails with an import error. Avoid these action names in a new world.
- **The default task pack.** `run_org_live` (and `ExperimentDesign` and the experiment loader in
  `oaos2/experiments/`) default to the task pack `paper_replication`, whose materials are not released.
  Always pass `task_pack`; the released launchers and examples do.
- **A leftover evaluator.** `oaos2/tasks/registry.py` imports and registers
  `paper_replication.numeric_compare` from `oaos2/tasks/plugins/paper_replication/`, and
  `oaos2/tasks/packs/paper_replication/` and `run_paper_replication_live` remain. The materials workshop
  does not use them. They are kept because the core imports them.
- **Comments and docstrings.** Comments in `oaos2/tasks/loader.py`, `oaos2/tasks/pack.py`,
  `oaos2/experiments/runner.py` and the workshop's `settings.py`, `vocabulary.py` and `derived.py`
  mention other workshop variants, the testing-firm pack and earlier tasks, and some cite design
  documents that are not released. They explain why code exists; they do not change behavior.

## Dashboard leftovers

The engine names no task: the materials workshop's live standings panel and its offline situation helpers live in
its plug-in (`oaos2/tasks/plugins/materials_lab/views.py` and `situation.py`), and the live page asks the run's
pack for its panel through an open registry (`register_standings` in `oaos2/dashboard/live.py`). A release test
(`tests/world/test_engine_names_no_workshop.py`) fails if code outside the task plug-ins names the workshop.

`/launch` lists experiment designs from `library/experiments/*.yaml`, of which this release has none, and calls
launch scripts that are not released, so it cannot start a run; its page also carries a paragraph about an
earlier task. A run's page labels some figures with the platform's general terms ("task scorer", "report
violations", the run's mode, "pilot"), which come from the platform's general scoring and do not measure the
competition study's outcomes; those are in the run's `derived/materials_lab_report.json` and in
`data/competition-9.2/runs.csv`. See the [dashboard guide](../DASHBOARD.md).

## What offline runs show

Offline runs, including `examples/quickstart.py` and the test suite, use scripted stand-in agents or
simulated model replies and `FakeContainerBackend`, which simulates containers without isolating
anything. They show that a configuration loads, that permissions and settings reach the agents as
intended and that the record is complete. They say nothing about how models behave, and passing them
does not show that real containers isolate the agents.

A scripted run in which no laboratory files a report, such as `examples/quickstart.py --study`, which
reads and waits, gets no credit and so scores as failed. That is the scorer's verdict on an empty run,
not an error. The tests that make paid calls or start real containers run only when `OAOS2_LIVE=1` is
set ([runbook](../RUNBOOK.md)).

## Models and providers

- **Models change.** A provider may retire a model or change what it serves under the same name, so a
  later run with the same model reference may not meet the same model. The competition study's own
  case is in [REPLICATION.md](../../REPLICATION.md).
- **Checks cover the models checked.** Adapters exist for Anthropic, OpenAI and three
  OpenAI-compatible hosts, but a new model can fail on a long tool-using task even when single calls
  work: it may reason up to its output limit without acting, or a provider may refuse a combination of
  settings. Try a short run before a series.
- **Reasoning differs by provider.** Some models return their reasoning text, others only a summary
  (OpenAI's Responses API, some Anthropic models) or none (OpenAI's Chat Completions). The record labels
  which kind it holds; reasoning text is not equivalent across models.
- **Safety refusals.** A reply the provider marks as a refusal is discarded and the call retried, up to
  four times in a turn; a workshop preset can end the run when refusals pass a bound. If refusals fall
  where an agent weighs the conduct a study measures, retrying keeps only the replies the provider lets
  through. The workshop's report counts where they fell.

## Costs and caps

- **Prices are a table in code.** `oaos2/pricing/table.py` holds dated price tables. A model with no
  row in any of them cannot be called: the workshop's launcher stops before the run, and other code
  fails at the first call. The prices are not refreshed from providers, and costs are computed from the
  table, not from invoices. An OpenRouter reference pinned to a host (`...@host`) needs its own row.
- **The cap is an estimate.** Before each call the ledger reserves an estimate of its input plus the
  maximum output. The input estimate is not a guaranteed upper bound for every model. A call resent after
  a timeout or server error may have been billed for each earlier attempt; the ledger holds such
  attempts at the call's projected cost against the cap (recorded as `held_usd` on
  `model.transport_retry` events), but recorded costs count only answered attempts.
- **One ledger per run.** All roles share it. Per-role costs and tokens are observed, not matched.

## Long runs

- **Context.** When an agent's conversation exceeds its context budget, the loop evicts old tool
  output, summarizes, and as a last resort cuts long incoming messages outside the recent turns to
  their first 600 characters. A model-written summary can itself be cut this way. The workshop's read
  tools return records and reports again, but anything that survived only in a summary can be lost.
- **The flat board.** The workshop's `read_board` returns every post after the number the agent
  gives, with no length limit; in a busy run this can fill a model's context. The forum form
  (`board: {form: forum}`) returns an index instead.
- **Oversized requests.** A request over the provider's context limit is refused and that agent stops;
  the others continue. Shortening an oversized tool result and retrying is not built.
- **Output limit.** A reply cut off by the output limit before any tool call is nudged once; if that
  happens again the agent's participation ends.
- **Container lifetime.** The runner's default container lifetime is 30 minutes. The workshop's launcher
  sets it from the preset's deadline; another launcher of a long run must set `wall_clock_cap` itself,
  or the agents' code tool stops working while the model calls continue.

## Containers and isolation

Containers support two network modes, `disabled` (the default) and `unrestricted`. The intermediate
modes `model_api_only` and `allowlist` need a host proxy that is not supplied, and a request for them is
refused with `docker.capability_gap`. The workspace size is checked after a tool finishes, so a running
tool can still fill the disk. Cleanup is best effort: a capture or isolation failure can leave a stopped
container for inspection. The [runbook](../RUNBOOK.md) shows how to find and remove one; select by the
run's `oaos2.mount_root` label, not by age, if other runs may be active.

## Other

- **Calls outside the record.** `scripts/materials_lab_debrief.py` asks each laboratory questions after
  a run by calling the provider directly, outside the spending ledger and the event record; its
  answers go to `derived/`. `scripts/materials_lab_comprehension.py` uses the ledger.
- **One large class.** `oaos2/tasks/plugins/materials_lab/pool.py` (about 2,200 lines) holds the
  workshop's configuration parsing, credit, report checks and deadlines in one class, switched by
  settings. A change there should be checked against the workshop's tests.
- **Engine features the workshop does not use.** Multi-party conversations have no working
  per-conversation cost limit (`max_cost_usd` is not enforced; run caps still apply). Scheduled notices
  have fixed content. Membership and authority cannot change during a run. Some mailbox settings
  (`topic_keyed` ordering, read receipts) are declared but inactive.
- **Example runs.** The competition study's example runs
  ([data/competition-9.2/example_runs/](../../data/competition-9.2/example_runs/README.md)) omit the providers'
  raw responses and reasoning text; views that need them show nothing.
- **A blind prototype can be identified.** A laboratory that measures a blind prototype whose recipe it has
  already measured on a full panel can learn the prototype's composition. This happens rarely and is reported
  where it occurs.

## Not yet built

- Changes of membership or authority during a run.
- Standard levels for most of the workshop's settings ([world/SETTINGS.md](../world/SETTINGS.md)).
- Off-chart messages delivered and recorded rather than refused; sanctions and rewards that change capacity or
  access.
- Spending limits per conversation; checks against paraphrased disclosure of restricted information.
- Network modes that allow selected outbound traffic.
- Compression of archives above 50 GB.
- Hard external quotas: costs come from a saved price table, not verified invoices.
- A model-based judge with its own spending limit.
- Recording a run's study, version and round in its own fields; today they are read from the experiment name.
- A confirmatory gate that accepts a family of fresh seeds.
- Spending budgets per role (one ledger per run); withholding the seeds of future confirmatory studies.

