"""Explain dashboard terms, status, provenance, and severity labels.

Templates use gh() for general terms and separate dictionaries for chips.
Definitions describe the fields actually calculated, including their limits.
A display label is not a complete check of research validity."""

from __future__ import annotations

# --- chip hover definitions ---------------------------------------------------- #

STATUS_HELP = {
    "completed": "The run ran to its end. Whether it can enter results and what it found are shown separately, as eligibility and outcome.",
    "passed": 'Completed with a recorded score that meets the task’s pass threshold.',
    "failed_score": 'Completed with a recorded score below the task’s pass threshold. This is a task result, not a run error.',
    "unscored": 'Completed, but no task score is recorded. Some studies deliberately report other outcomes instead.',
    "invalid_archive": 'The saved status reports failed archive checks. Inspect the event record before using derived results.',
    "stalled": 'The supervisor recorded a deadlock timeout: work could not make progress within its time allowance.',
    "run_failed": 'A run.failed event was recorded. Inspect its reason separately from the quality of submitted work.',
    "incomplete": 'No terminal run event is recorded. The run may still be active or may have been interrupted; saved results are partial.',
    "idle": "No terminal run event, and the record has not moved for two days. Read as not in flight; saved results are partial.",
    "empty": 'No events were found in the run’s event streams.',
}

PROVENANCE_HELP = {
    "gate-check": 'The experiment name suggests a materials check. Verify the study design; this naming tag does not establish the purpose or validity of its results.',
    "current": 'The saved reference hashes checked by this view match the library. This does not check every condition needed to compare runs.',
    "stale_materials": 'A checked scoring reference or task manifest differs from the current library. Interpret the run using its original materials.',
    "superseded": 'The task pack or organization preset is no longer in the library. The saved run remains a historical record.',
    "unknown": 'The saved references are insufficient for comparison, or the current task pack could not be loaded.',
}

SEVERITY_HELP = {
    "critical": 'A problem that can undermine the event record; inspect before using results.',
    "serious": 'A possible threat to the study’s interpretation that needs review.',
    "warning": 'An unusual condition to inspect.',
    "info": 'A recorded condition that may help explain the run.',
}

# --- the general glossary ------------------------------------------------------ #

GLOSSARY = {
    # run identity
    "run": 'One execution attempt with specified task, organization, model, and resource settings. It can be complete, active, or interrupted.',
    "experiment": 'A named study design or batch. Its runs can be grouped by the conditions tested.',
    "organization": 'The arrangement of roles, information access, authority, and communication tested in a run.',
    "model": "The displayed model reference, usually the run default. Individual roles can override it; inspect the saved role-model assignments.",
    "difficulty": 'The task condition selected by the design. Its meaning comes from the task materials, not a universal easy-to-hard scale.',
    "mode": "pilot explores; calibration checks materials and capacity; confirmatory tests registered predictions under stricter checks.",
    "task pack": "The packaged task: materials, prompts, deliverable contracts, and "
                 "scoring — versioned as one unit in the library.",
    "run dir": 'The folder holding this run’s settings, event record, model responses, and saved files, to the extent retained.',

    # scores & outcome
    "v0 plan score": 'The initial plan’s score at submission. Clocked budget-execution studies use separately declared outcomes such as retained fraction.',
    "score": 'The task evaluator’s measure of submitted work. Its scale and pass threshold are defined by the task.',
    "partial score": 'A graded measure of task performance, often from 0 to 1. Read the task’s scoring rule to interpret it.',
    "passed": "Whether the submission met the pass bar.",
    "label": 'assisted means a recorded or treatment-defining intervention lies on a recorded causal path to a commitment; unassisted means none was found on those paths.',
    "disposition": 'How the event record ends: completed, failed, stalled by a timeout, or incomplete without a closing event.',
    "outcome closed": 'Whether an outcome.closed event was recorded after a contract’s completion rule was met. This is separate from score and run completion.',
    "scored": "Whether an evaluator produced a score. A valid completed run may be "
              "deliberately unscored; that is not the same as failing.",
    "retained fraction": "The share of baseline program benefit preserved after the "
                         "dynamic execution shocks, repairs, lateness, and unresolved cases.",
    "commitments": 'Accepted submissions or decisions that count toward the task’s completion rules.',
    "handoffs": 'Recorded transfers of work between agents. Their saved source and payload can be compared to study which information was retained.',
    "conversations": 'Discussions with two or more participants taking speaking turns.',
    "registered experiments": "Runs whose manifest declares confirmatory mode. The preregistration says how their pass and fail results are read.",
    "exploratory work": "Runs declared calibration or pilot: checks, probes, smoke runs. Results are recorded, not findings; whether one counts is the study’s decision.",
    "started": "When the run began, in this computer’s local time, read from the run identifier. It orders the lists and is not an analysis input.",
    "needs attention": "Runs with a recorded condition to read first: censored, mechanical floor, a crash, an unfinished ending, or an unexplained report error.",
    "eligibility": "Whether the run can enter results: it finished, closed its outcome, and meets the task's criteria. A study's saved dataset decides when there is one.",
    "outcome": "The task's central measure for this run: the scorer's pass/fail, unless the task defines its own outcome.",
    "task result": "The fixed scorer’s verdict on an exploratory run, shown muted because the run was not a registered test.",
    "board posts": "Messages an agent chose to post for every agent in the run. Delivery and explicit reads are recorded separately; neither shows understanding.",
    "notes": "Private messages an agent chose to send to one role. Delivery and explicit reads are separate records; neither shows understanding.",
    "communication grants": "The board and note actions the preset lets a role call. A grant is what was available, not what was said.",
    "exchanges": "Directed acts the task registers between agents, such as a grant or a share. The list shows who acted toward whom and when.",
    "exchange threads": "A reading aid: a message followed by what its addressees then did toward the author. Grouped by proximity, not shown to be replies.",
    "evaluation": 'A scoring record with participant feedback separated from private researcher diagnostics.',

    # validity & audit
    "archive valid": 'Whether the recorded archive checks passed. These check internal consistency, not every requirement for valid research.',
    "parity regime": "Whether comparison arms receive matched resource limits: budget_matched uses the declared basis; unconstrained does not match it.",
    "exposure confounded": 'A detected mismatch in the declared model information or reasoning exposure. Review the finding before comparing arms.',
    "context budget": "An added token limit on the text kept for an agent’s model requests. No value means no study-specific cap; model limits still apply.",
    "interventions": 'Recorded platform actions such as retries, timeouts, or corrections, classified by their possible effect on the result.',
    "terminal record": 'An event declaring the run completed or failed. NONE means no such event was found; the run may be active or interrupted.',
    "irregular": 'An agent.failed or run.failed event was found. Inspect its cause and any effects on the result.',
    "censored": "A wind-down or agent failure was recorded. Inspect its cause; the study's "
                "analysis rules determine exclusion or separate reporting.",
    "floor regime": "No role demonstrated more than one completed disposition per round; "
                    "the observation cannot establish usable parallel capacity.",
    "viol.": "Protocol violations: times an agent tried something its organization's "
             "rules forbid (wrong channel, unauthorized submission, …).",

    # cost & resources
    "cost": 'Cost calculated from reported model usage and the run’s saved price table. It is not an independently checked provider invoice.',
    "cap": 'The configured spending limit. The gateway refuses a new call when its estimated cost plus spent and reserved funds would exceed it.',
    "tokens": 'Model text units counted for input and output usage. These counts are not measures of knowledge, reasoning quality, or useful information.',
    "model calls": 'The number of recorded model invocations, including calls for actions or context summaries. A call is not a fixed unit of reasoning.',
    "agents": "How many AI agents worked in this run.",
    "events": 'The number of recorded events, such as observations, tool calls, messages, and submissions. This does not reveal unreported internal model activity.',
    "pricing table": "The price list used to compute costs, fingerprinted so cost "
                     "figures are reproducible.",
    "image": "The recorded container image digest, or the image reference if no digest is available. A mutable tag alone does not identify exact image contents.",
    "reference": 'A content hash identifying saved scoring materials. The provenance check compares available hashes with the current library.',
    "schema": "The version of the event-record format.",
    "source commit": "The recorded Git revision. A dirty-worktree hash can detect differences, but reconstruction also requires the actual changed files; hashes do not contain them.",
    "apparatus": 'A content fingerprint of experimental code and materials, used to identify which implementation produced a run.',

    # logical clock and capacity
    "clock": "The logical-time condition used by this experiment.",
    "logical clock": "Experimental time measured in declared rounds or working days, not "
                     "wall-clock minutes. It makes arrivals, deadlines, and capacity comparable.",
    "clock label": 'A short name for the experiment’s declared work schedule, such as r16w3. Interpret it using that design’s clock settings.',
    "schedule variant": "The hash-pinned arrival/deadline schedule paired with a clock condition.",
    "deadline lapses": "Cases or plan commitments that crossed their declared due round. "
                       "This is graded lateness, not a protocol violation.",
    "megabatch": 'Whether a role can handle several submission slots in one logical day, subject to the configured call limits.',
    "slot ceiling": 'The allowed model calls for one bound submission slot before its declared fallback is considered.',
    "contract profile": 'The selected set of required submissions, their dependencies, and the rule for completing an outcome.',

    # trace / events
    "seq": 'The writer-assigned sequence number used to order events. Timestamps are advisory.',
    "turn": "One agent work cycle: the agent looks at its situation, thinks, and acts.",
    "phase": "Which stage of the run this happened in: setup, execution (the actual "
             "work), closure (scoring and teardown), or infrastructure.",
    "audience": 'The event’s intended visibility category. agent marks participant-facing information; it does not prove delivery to every agent.',
    "channel": "The event’s declared communication category. Labels do not override the organization’s permissions; scoring and infrastructure are internal.",
    "family": "The first part of an event's name — tool.*, model.*, file.*, "
              "conversation.* — a coarse grouping.",
    "event class": "The specific kind of event, e.g. tool.called or state.committed.",
    "events by class": "A count of each kind of event — a quick fingerprint of what "
                       "kind of activity dominated this run.",
    "causality": 'Recorded links from an event to earlier events that contributed to it. These are evidence for process analysis, not a complete causal explanation by themselves.',
    "volley": "One speaking turn in a group discussion.",
    "derived views": "Transcripts, file histories, and metrics rebuilt from saved evidence. Same inputs and code give the same output.",
    "raw config": 'resolved.json saves resolved settings; manifest.json records run identity, versions, and content fingerprints.',
    "annotations": "Your own analytic marks on this run's events — stored beside the "
                   "record, never inside it.",

    # library / launch
    "factors": "The experimental dimensions swept: each combination of values becomes "
               "one cell (a set of replicated runs).",
    "replications": "How many times each cell is repeated, to average over noise.",
    "contract profiles": "The deliverable structures this task supports, such as one submitter, analysts feeding an orchestrator, or a deliberating committee.",
    "evaluators": "The automated graders this task registers.",
    "tiers": "The task's difficulty conditions and their materials.",
    "ignored keys": 'Configuration fields identified as unused by the loader. Their presence in a file does not make them active controls.',
    "scheduler": 'The rule for admitting ready agents to work. The runtime also handles waiting dependencies; clocked_rounds adds logical-day limits.',
    "committer binding": "Who may make formal submissions: by_role = only the role "
                         "the contract names; any = any member.",
    "live coordination": 'The procedure that arranges work among roles, such as staged reporting or group discussion, with its declared settings.',
    "attention": 'The task-material scope assigned to a role. Additional notice scopes, if configured, are separate.',
    "plays": 'Task-role names this agent can fulfill when submissions are assigned. Each Role entry creates one agent; plays does not set the number of copies.',
    "cell": 'One combination of the design’s factor values, such as organization, task condition, model, and capacity. Repeated runs share that setup.',
    "reps": "How many repeated runs per cell (replications).",
}
