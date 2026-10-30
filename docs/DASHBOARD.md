# Using the dashboard

The dashboard is a local web application for reading run archives: following a run while it is
written, replaying a finished one, reading what the agents said and did, and comparing runs. Every
view is built from a run's saved event record and files; viewing a run never changes them. The
code is in `oaos2/dashboard/` (routes in `app.py`, pages in `templates/`); [SYSTEM.md](SYSTEM.md)
describes the archive it reads.

## Starting it

```bash
uv run python scripts/dashboard.py <runs folder> --port 8722
```

Pass the folder that holds the runs, for example `examples/runs` after the quickstart, or `runs`
(the default) after a live launch. Open <http://127.0.0.1:8722>. The server listens only on this
computer. The first visit builds indexes and reports, which it keeps in `<runs folder>/.dashboard/`;
these can be deleted and are rebuilt. `/runs?rebuild=1` rebuilds the run index. Pages show the
archive as it is when loaded; refresh to see new activity, except on the live pages, which update
themselves.

**Example runs.** The competition study's example runs, in
[data/competition-9.2/example_runs/](../data/competition-9.2/example_runs/README.md) (open them with
`uv run python scripts/dashboard.py data/competition-9.2/example_runs --port 8722`; see
[REPLICATION.md](../REPLICATION.md)), open like any other run, but they were published without the providers' raw responses (the `raw/`
folder) and without the reasoning text the providers returned with each reply. A "raw payload" link
on an event page therefore shows "not found", and the deepest reading levels show no reasoning text.
Everything else in the record is as the run wrote it.

## Across runs

| Address | What it is for |
|---|---|
| `/` | Overview: what the platform records, and a snapshot of the archive: run counts, runs in progress, the most recent runs |
| `/runs` | The run list. Each row gives the start time, preset, model, run state, eligibility and the task's outcome; filter by experiment, organization, model, status or text. Runs of one experiment with several seeds are grouped into one entry (`group=0` lists every run); `blind=1` hides outcomes |
| `/registry.csv` | The same list, with the same filters, as a CSV file |
| `/experiment/<id>` | All runs of one experiment side by side, with their conditions and outcomes |
| `/experiment/<id>/cases` | A table of cases across the runs of an experiment, for case-based tasks; the materials workshop has no cases |
| `/design/diff?a=<run>&b=<run>` | The differences between two runs' settings and role texts. It shows what differed; it does not by itself show that only the intended treatment did |
| `/live` | Runs that may still be being written, most recently written first |
| `/search` | Text search over notices, reports, messages and model text within one experiment or lineage (a scope is required), with links to the source events |
| `/study-records` | The study records saved in `docs/experiments/`: the index, the preregistration and the results pages |
| `/annotations`, `/codebook` | Researchers' labels across runs, and the definitions of the labels in use |
| `/library`, `/library/edit` | The presets and task packs in `library/`, as the loaders resolve them; an edit is saved only if the real loader accepts it, otherwise the file is restored |
| `/cleanup` | Dead runs: no events, failed or stalled, a failed archive check, an agent crash, or stopped without finishing. Removing one moves its folder unchanged to `<runs folder>/.removed/`, and it can be restored; nothing is deleted. Confirmatory runs and runs in a frozen analysis dataset cannot be removed here |
| `/launch` | A launch form for experiment designs. It lists none in this release and cannot launch; use the launchers in the [runbook](RUNBOOK.md) |

A run's **state** says whether it ran to its end (completed, incomplete, failed, stalled, idle). A run
with no closing event is incomplete: it may still be running or may have been interrupted; after 48
hours without a change it is shown as idle. The **outcome** is the task's own measure. For the
materials workshop the scorer passes a run on any credit, so the dashboard shows beside it what the
record says before any coding: in the competition study's form, whether a laboratory filed a report
using the supplier variant the association asked members not to use; otherwise, whether a laboratory
filed a report that the private assessment found in violation. Neither is coded conduct. A scripted run in which no laboratory files a report, such
as `examples/quickstart.py --study`, therefore shows as failed: that is a valid score, not an error.

Material-version labels (`current`, `stale_materials`, `superseded`, `unknown`) say whether a run's
pinned materials still match the library; they are a warning, not a test that two runs are comparable.

## One run

A run's pages share a row of tabs: Overview, Story, Replay, Organization, Agents, the task's work tab
(for the workshop, **Projects**), Record and Annotations, plus **Live** while the run may still be
written and **Days** for runs on a logical clock. `<run>` below is the run folder's path within the
runs folder; the dashboard builds these links.

| Address | What it is for |
|---|---|
| `/run/<run>` | Overview: preset, model, state, outcome, cost, the task's report card, and any conditions that affect how the run may be read |
| `/run/<run>/story` | The organization's life in order, in the agents' own words. When the run had a board, its posts are the spine; a depth control adds private notes and notices, then what each agent said, then tool calls and reasoning text |
| `/run/<run>/replay` | The record played back against the time since the run began: the messages one at a time or at 10× to 120× speed, and a graph of who dealt with whom in the current window |
| `/run/<run>/live` | For a run being written: where each agent is, who is dealing with whom, and the newest items. It checks for new events every three seconds and stops when the run ends |
| `/run/<run>/organization` | Who was in the run, what each role could do (its communication grants, tools and model), and a graph of the messages and exchanges between roles |
| `/run/<run>/design` | The conditions as assigned to this run, compared with the current library preset, and which channels and rights were actually used |
| `/run/<run>/agents`, `/run/<run>/agent/<id>` | One profile per role: what reached it, what it did, what it cost, and problems recorded around it |
| `/run/<run>/comms` | Voluntary communication: board posts, notes between pairs of roles, and the task's exchanges (for the workshop, granting measurements and sharing records), with explicit reads counted separately from delivery |
| `/run/<run>/flow` | Everything in sequence with the text of actions and decisions, at a chosen level of detail, with citations to copy |
| `/run/<run>/work` | The task's own account of the run (the **Projects** tab for the workshop: the institution's outcome, conduct by laboratory, reporting opportunities, projects, laboratories, reports, concerns and retirements), computed from the record by the plug-in's reader |
| `/run/<run>/cases`, `/run/<run>/case/<id>`, `/run/<run>/casebook.md` | Case histories for tasks built around cases, read blind by default; the workshop's projects use the work tab instead |
| `/run/<run>/days` | Roles by logical day, for clocked runs; workshop runs are not clocked |
| `/run/<run>/files` | The files the agents created or changed |
| `/run/<run>/record` | The verification layer: archive checks, how the run ended, diagnostics, pins and their match with the library, events by class, and the derived files |
| `/run/<run>/audit` | Problems and platform interventions, and spending over the run against its cap |
| `/run/<run>/trace` | The raw event list, filterable by agent, event class, channel, turn or text |
| `/run/<run>/event/<id>` | One event in full: its fields, the events that caused it and those it caused, a citation line, and a link to the provider's raw response when the archive has it |
| `/run/<run>/annotations` | Labels researchers attached to this run's events |
| `/run/<run>/derived/<file>` | A file from the run's `derived/` folder |

A message delivered to a role is not a message it read, and reasoning text is the text the model
returned, not access to its computation. Arrows and counts show what was sent or granted.

An event page's citation line names the run, the event, its position and a content fingerprint;
`scripts/cite.py` resolves it or checks the citations in a notes file ([runbook](RUNBOOK.md)).
Annotations are appended to the run's `annotations/` folder, apart from the event record; they are
research data that cannot be rebuilt from it. A task report saved in `derived/` is shown as saved;
when none is saved, or the saved one lacks fields the current reader produces, the dashboard computes
one with the current code and labels it so.
