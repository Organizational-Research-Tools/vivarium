# Why the platform is designed this way

Vivarium (Python package `oaos2`) compares how organizations of AI agents work under controlled conditions. Its design
must support two things at once: changing an organizational arrangement and preserving a
record detailed enough to explain the resulting behavior.

This document explains the design choices. [SYSTEM.md](SYSTEM.md) locates their
implementations; [DEFERRED.md](mechanism/DEFERRED.md) records their current limits.

## Keep the experimental parts separate

Tasks specify the work and scoring. Organizations specify roles, information access,
communication, authority, and scheduling. Agents carry out those roles using selected
models. The execution machinery runs tools and records activity.

This separation lets a study change one part while holding others fixed. A role can use
a different model without changing its responsibilities. A task can use a different
organization without changing its answer key. These are possibilities the design supports;
each actual comparison still needs checks for unintended differences.

## Record evidence before interpreting it

The engine records messages, model responses, file changes, submissions, and interventions.
Analysis code uses those records to investigate concepts such as information loss or
accepting a good-enough answer. Keeping those interpretations out of the engine lets
researchers revise or compare explanations without rewriting the original evidence.

There is one event writer per run. It appends events without changing earlier entries,
assigns their sequence numbers, and preserves links to preceding causes. Events waiting
to be written are stored in a durable queue, so recovery can resume from saved entries.
Transcripts, indexes, and dashboards are rebuilt from the evidence. They must not maintain
an independent account of what happened.

## Own the agent loop

The platform assembles each model request, receives the response, checks requested actions,
and returns the results. Provider adapters translate individual requests and replies;
they do not control the sequence of agent actions. An **adapter** is the small module that
converts between the platform's common format and a provider's format.

Owning this loop makes the action sequence observable and keeps provider-specific behavior
in one place. It also prevents an external agent-running library from silently changing
how tools or conversations work between experiments.

## Isolate tool use and protect the evidence

The host computer manages the run and keeps credentials. Docker containers isolate agents'
tool execution. Writable workspaces are backed by host files so container failure need not
destroy captured work. Hidden scoring keys stay outside the participant workspace, and
containers cannot rewrite accepted submissions.

Information restrictions are part of the experiment: an uncontrolled communication route
can change who knows what. State the actual enforcement strength. File permissions can
block access; a text-copy check cannot guarantee that an agent never paraphrases restricted
information. The limitations list takes precedence over the original design's ambitions.

## Let the organization determine work order

Agents have independent loops and may work at the same time. A **scheduler** decides which
ready agents may act. Work dependencies can require one report before another role proceeds;
a conversation can pause its requester without pausing every agent.

Thus sequential and parallel arrangements can be experimental choices. The event writer
still produces one ordered record. Clocked experiments add defined work periods and
deadlines; these logical periods are distinct from elapsed seconds.

## Add research through configurations and plugins

Use a configuration when the engine already supports the desired behavior. Use a plugin
when a task needs its own scorer, reporting method, or coordination procedure. A plugin
implements an agreed interface: what it receives, what it returns, and what it may change.

A **registry** is a validated list of available implementations or vocabulary entries.
Register a new scorer or message kind there instead of adding task-name branches to the
shared engine. Keep the basic record structure stable while allowing new registered uses.
A setting reserved for future use is not a working feature.

The repository calls the extension test the **zero-diff gate**: adding a task or theory
package should leave shared engine code unchanged. If an experiment needs a genuinely new
engine capability, first specify the general interface, its named research use, and how it
will be checked. Then document the change in the limitations list and system map.

## Match resources before the run and measure use afterward

A study declares its resource comparison in advance. The platform calls this **parity**:
for example, equal assigned output-token budgets. Actual calls, text output, and spending
are recorded as outcomes or possible explanations of the treatment effect. They must not
be silently used to select comparable-looking successful runs afterward.

Confirmatory work requires preregistered analysis, matching calibration evidence, recorded
interventions, and the required data retention. Readiness checks and explicit launch
permission remain separate. A passed offline test verifies machinery, not a scientific
prediction or behavior on every model provider.

## Where to read further

[SYSTEM.md](SYSTEM.md) maps where each responsibility lives in the code, [WORLD.md](WORLD.md) explains how a
study is built on the materials workshop, and [mechanism/DEFERRED.md](mechanism/DEFERRED.md) lists what is not
yet built or not yet complete.
