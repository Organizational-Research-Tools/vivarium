# Runbook

Run these commands from the repository directory. Angle brackets mark values you must replace.
This runbook is the public release's version of the project's runbook: it keeps the commands for
what this release contains, the materials workshop and the platform around it.

Offline checks use simulated models and containers and cost nothing. Live runs call model
providers, are billed to your keys, and need Docker. No command below spends money unless it
carries `--go`.

## 0. Install

Use Python 3.11 or later. With [uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-extras
```

Then prefix the commands below with `uv run`. With `pip` in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,dashboard,live]"
```

and run them as `PYTHONPATH="$PWD" python …`. The `dev` extra holds the test tools, `dashboard` the
local web server, and `live` the Anthropic and OpenAI SDKs and environment-file support.

For live runs, keep credentials in the environment or in a `.env` file at the repository's root (a `.env` in a
folder above it is not read), outside version control and outside the agents' containers. Configure only the providers you use: `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, or the key of an OpenAI-compatible host for open-weight models
(`TOGETHER_API_KEY`, `OPENROUTER_API_KEY`, `OPENCODE_API_KEY`). Build the agents' container image
once:

```bash
docker build -t oaos2-science:py311 -f docker/Dockerfile docker
```

## 1. Check the installation

```bash
python -m pytest tests -q
```

The test files that can make paid calls or start real containers
(`tests/models/test_anthropic_adapter.py`, `tests/docker/test_live_docker.py`) are left out of
collection unless the environment sets `OAOS2_LIVE=1` (`tests/conftest.py`), so a plain run never reads credentials or contacts
Docker. Set it only when you intend to pay for those calls. Check failures and skip reasons:
missing `pytest-asyncio` can silently skip asynchronous tests, and skipped or excluded checks have
not passed.

A quicker check of the materials workshop, the event record and the dashboard:

```bash
python -m pytest tests/tasks/test_materials_lab_pack.py tests/archive tests/dashboard -q
```

## 2. An offline run

```bash
python examples/quickstart.py
```

This runs one organization of the materials workshop with scripted stand-in laboratories and simulated
containers, and writes its archive under `examples/runs/` (`--study` runs the competition study's
preset). `--preset <preset>` runs any preset in `library/organizations/`, a study of your own among them,
with laboratories scripted to read their situation and wait; `examples/new_study/run_offline.py --arms
<control> <treatment>` checks, compares and runs two. See [examples/README.md](../examples/README.md).

## 3. Open the dashboard

```bash
python scripts/dashboard.py examples/runs --port 8722
```

Open <http://127.0.0.1:8722>. The dashboard listens only on this computer. The first scan may take
longer because it builds reusable indexes and reports; `/runs?rebuild=1` rebuilds the run index.
Refresh pages to see new activity. To read another archive folder, pass it instead of
`examples/runs`. The [dashboard guide](DASHBOARD.md) explains the views.

## 4. Read and verify saved evidence

List runs or export their index:

```bash
python scripts/run_registry.py examples/runs
python scripts/run_registry.py examples/runs --csv registry.csv
```

Copy an event citation from the dashboard, then resolve it, or check every citation and same-line
quotation in a notes file against the archive (exit status 1 if one fails):

```bash
python scripts/cite.py '<paste the complete cite: line here>'
python scripts/cite.py --check path/to/your-notes.md
```

To regenerate a run's derived transcripts and reports from its event record:

```bash
python -c "from oaos2.archive.export import render_archive; render_archive('<run_dir>')"
```

The same evidence and analysis code produce identical bytes; changed analysis code may change
reports.

A materials-lab run is summarized by `scripts/materials_lab_report.py`. The competition study's
results are regenerated from its derived data; see [REPLICATION.md](../REPLICATION.md).

## 5. A live run of a preset

First print the plan, which spends nothing:

```bash
python scripts/run_materials_lab_smoke.py --preset competition_competitive --model openrouter/z-ai/glm-5.3-flash@z-ai --reasoning-budget 1000 --seed 41 --cap 15
```

It names the preset, the seed, the deadline, the model and the number of calls, and estimates the
spending. Its cost guard refuses a cap below the minimum it computes (and exits with code 2), so that
a run is not cut short when the ledger stops admitting calls. For this example, GLM-5.3-Flash through
OpenRouter, the cheapest of the competition study's models, the guard expects about $10 and requires
a cap of at least $13, priced from the model's rates; once runs of a model are recorded under `runs/`,
it uses their observed spend instead, and `--guard-rate` fixes the rate for a study. The competition
study's GLM runs cost about $1.60 each. Add `--go` to launch; the run is
billed to your key. `--model` selects the model (an OpenAI-compatible host's models are named as in
`openrouter/<provider>/<model>`), and `--calls` the model calls per laboratory (40 by default, which
ends a fifty-minute run early; the competition study allowed 1,500). Afterwards, read the run with the
command the launcher prints.

Any preset can be launched this way, including a study of your own written as an overlay on the
workshop ([WORLD.md](WORLD.md)). Check it first with
`python scripts/compare_presets.py <control> <treatment> --check`.

To run one cell of the competition study's main study again, with exactly the plan's settings, use
`scripts/run_plan_cell.py` ([REPLICATION.md](../REPLICATION.md)):

```bash
python scripts/run_plan_cell.py glm53 competitive 41
```

## 6. Monitor and stop a run

Follow a run on the dashboard's `/runs` page. To stop a materials-lab run early, send its launcher
one SIGINT (Ctrl-C in its terminal, or `kill -INT <pid>`) or SIGTERM. The run then stops
dispatching model calls, ends its work period, writes a valid archive and removes its containers,
usually within a minute; its report records the end reason `stopped_by_pi` (the code's name for a stop by the person running it). Wait for that rather
than signalling again: a second signal forces an exit and can leave a partial archive and
containers behind. A killed run keeps only a partial trace, which the run index marks incomplete.

If a stopped run leaves a container behind, find it and remove only that container:

```bash
docker ps --filter ancestor=oaos2-science:py311
docker rm -f <confirmed_orphan_container_id>
```

## 7. Change the materials

Task packs live under `library/tasks/`, organization presets under `library/organizations/`. The
dashboard's `/library/edit` validates edits with the real loaders. Read a pack's
`INSTRUMENT_DESIGN.md` before changing it, keep frozen versions, and create new versions for
successors.
