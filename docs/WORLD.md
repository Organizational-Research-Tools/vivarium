# The materials workshop as a world

Vivarium separates three layers. The **engine** runs organizations of agents: the agent loop, tools and
permissions, the spending ledger, the event record and the dashboard. A **world** is a task the engine
runs: it generates instances, defines the actions agents may take, scores their work, provides a base
organization and standard texts, and supplies readers that turn the event record into measures. A
**study** changes a few settings of a world. It is written as presets, not as code.

This repository carries one world, the materials workshop. This page explains its parts, how a study is
built on it, and what is not yet standard. [world/SETTINGS.md](world/SETTINGS.md) describes every setting,
and [examples/new_study/](../examples/new_study/README.md) works through a study from start to finish.

## The workshop

Laboratories develop materials for a client. A material is a recipe that sets each of twelve components
to one of four levels. The client accepts a recipe only if it performs well enough on three tests: heat
resistance, mechanical strength and water resistance. Each laboratory owns the instrument for one test, so
laboratories must test one another's prototypes and pass the results to whoever submits, and every test
draws on a limited budget. A generator builds each set of projects from a seed and knows which recipes
would pass, so the same projects can be posed to differently organized laboratories, and correct results
can be told from false ones in the record.

## Its parts

The workshop is a plug-in: the engine does not depend on it, and a release test fails if code outside the task
plug-ins names it ([known limits](mechanism/DEFERRED.md)). Its parts are:

| Part | Where | What it does |
|---|---|---|
| Task pack | `library/tasks/materials_lab/` | The manifest declares the actions, the role texts and the evaluator; `assets/prompts/` holds the role texts; `INSTRUMENT_DESIGN.md` is the task's dated build record, kept as frozen, which names records that are not released |
| Instance generator | `oaos2/tasks/plugins/materials_lab/landscape.py` | Builds a set of projects from a seed and verifies over the whole recipe space which recipes pass |
| Actions | `actions.py` | The laboratories' tools: registering prototypes, granting and taking measurements, sharing records, filing reports, the board and notes |
| Rules and scoring | `records.py`, `pool.py`, `evaluator.py` | Measurement records, report scoring, credit, publication and the end of a run |
| Coordination | `protocol.py` | Binds each laboratory to its credit, runs the pool beside the agent loops, delivers results and messages |
| Presentation | `presentation.py`, `vocabulary.py` | What a laboratory sees of the instance: codes, names, order and units |
| Settings check | `settings.py` | Refuses, before any run, a setting the workshop does not read and a combination it would read and then ignore |
| Readers | `derived.py`, `scripts/materials_lab_report.py` | The run report (per laboratory and per project, against the generator's truth) and the exchanges the dashboard's communication views show |
| Base organization | `library/organizations/materials_workshop.yaml` | Six laboratories and every setting of the competition study that its two arms shared |

## How a study is built on it

A study is a set of presets in `library/organizations/`. A preset that names `base:` lists only what it
changes in that base:

- Mappings merge key by key. Any other value, such as a list, a number or a text, replaces the base's
  whole value. An overlay can set or replace a setting but cannot remove one.
- An overlay gives its own `preset_id`. A preset marked `base_only: true` is a base for others and is not
  run alone. Bases can chain. A loop of bases, or a missing base, is refused.
- When a preset loads, the workshop checks its settings, so a misspelled setting fails before any run and
  names the setting.
- `scripts/compare_presets.py <a> <b> --check` loads two presets as a run would and lists every setting
  in which they differ, with their bases applied and texts compared sentence by sentence.
- Every run records its preset and each base it rests on, with their sha256, in the archive's
  `manifest.json` (`extensions.organization_bases`). The dashboard marks a run whose preset or bases have
  changed since it ran.

The competition study shows the form. Its two arms are
`library/organizations/competition_competitive.yaml` and `competition_cooperative.yaml`. Each is the
workshop plus the arm's credit institution and the three texts that state its objective, its urgency and
its deliberation topic; the competitive arm also sets divisible credit and the success floor and cap.
A test (`tests/world/test_world_presets.py`) checks that each resolves, setting for setting, to the
preset the study's main study ran (`pc1_supplier_g_xmodel7.yaml` and `..._cooperative.yaml`, kept as
frozen).

## What a study can vary

[world/SETTINGS.md](world/SETTINGS.md) groups the settings by the seven parameters along which the research
proposal will limit the workshop's design space: the interdependence of components and instruments; the structure
of communication and authority; the formal rules and whether their stated rationale holds; the interests assigned
through credit and scarce resources; surveillance and sanction; the equivocality of client signals; and the history
inherited from earlier members. A last group holds the workshop's mechanics, which a study normally leaves as they
are.

Some parameters already have released levels. The formal rule has three stated reasons (`rule_level`:
`approved_list`, `licence`, `injury`); the credit institution is `competitive` or `cooperative`; credit
is `exclusive` or `divisible`. The other parameters have none: interdependence, structure, surveillance and
sanction, equivocality and history are set by free numbers, switches and texts, and a study that changes a text
replaces the whole paragraph. The structure of communication and authority is written mostly outside
`live_coordination`, in the preset's roles and channels. The workshop has no lead or hierarchy setting, and declared
channels narrow private notes only.

## What the workshop suits

The workshop's generated landscapes and divided instruments suit collaborative search. Its recorded filings and
credit suit rule avoidance, competition and cooperation. It suits informal organization poorly: in development
studies, when a formal channel stalled, members mostly waited and no workaround became a convention, because the
stall created no coordination problem that informal rules could solve. The proposal leaves informal organization
to a separate world.

## What is not yet standard

The workshop grew study by study, and Vivarium is a prototype. A study on it today should expect:

- **No standard levels for most parameters.** Many settings are free texts or numbers, and five of the seven
  parameters have no released levels ([world/SETTINGS.md](world/SETTINGS.md) says which). Making each parameter
  changeable at a few standard levels, and measuring for each model how agents respond at each level, is the
  development work the proposal describes.
- **One tested base.** `materials_workshop` is the configuration the competition study ran at scale. Other
  configurations of the same settings have been run in development studies only; their presets are kept
  as test fixtures in `tests/fixtures/organizations/`, where `OAOS2_ORGANIZATIONS` lets the loader find
  them.
- **Settings that are recorded but have no effect in that base.** `density` is overridden by
  `difficulty_ladder`; `instance_seed` is replaced by the launcher's `--seed` on every run; an audit
  probability selects no report in the contest form (it still routes concerns to the portal's log).
  [world/SETTINGS.md](world/SETTINGS.md) notes each case.
- **Texts carry the conditions.** Agents read the texts a preset gives. A study that changes them should
  describe the situation plainly, as an employer would, and avoid sentences that point at the conduct
  under study.
- **Scripted runs test configurations, not behavior.** The offline runs in `examples/` show that a
  configuration loads and reaches the laboratories as intended. Only runs with models show how agents
  respond, and they cost money ([RUNBOOK.md](RUNBOOK.md)).

## Adding another world

A new world is a task pack under `library/tasks/<name>/` and a plug-in under `oaos2/tasks/plugins/<name>/`:
a manifest naming its actions, role texts and evaluator, a coordination procedure (`protocol_module`), a
`validate_settings` function that refuses settings it does not read, and readers for its records. The
engine needs no change. [SYSTEM.md](SYSTEM.md) and [ARCHITECTURE.md](ARCHITECTURE.md) describe the
contracts the engine offers.
