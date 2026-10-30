# Quickstart: an offline run and the dashboard

This example runs one organization of the materials workshop without a model, an account, Docker, or
spending, and then opens the dashboard on the run's archive.

```bash
uv sync --all-extras
uv run python examples/quickstart.py
uv run python scripts/dashboard.py examples/runs --port 8722
```

Then open <http://127.0.0.1:8722>. The run takes a few seconds.

## What runs

The materials workshop's laboratories develop recipes for a client. A recipe is qualified when panels on
three test instruments (heat, strength, water) show that it meets the client's target, and each
laboratory owns one instrument, so qualification takes the work of all three. The task pack is
`library/tasks/materials_lab/`; [docs/WORLD.md](../docs/WORLD.md) describes it, and that folder's
`INSTRUMENT_DESIGN.md` is its dated build record.

By default the quickstart loads the preset `library/organizations/materials_trio.yaml`: three
laboratories, one per instrument. Instead of models, scripted stand-in laboratories act through the
workshop's real tools (the stand-ins are the test suite's, in `tests/tasks/test_materials_lab_pack.py`): one registers a recipe,
grants the others access, measures a panel and asks for the other two; they measure and share their
receipts; it files a report citing all three, which the client scores and credits. The platform
runs them as it runs model agents: the same agent loop, the same permission checks, simulated
containers (`oaos2.docker.backend.FakeContainerBackend`), and the same event record.

`--study` loads the competition study's competitive arm, `competition_competitive.yaml`: the
materials workshop (`materials_workshop.yaml`) plus the arm's credit institution. It resolves to the
preset the study's main study ran, `pc1_supplier_g_xmodel7.yaml`, setting for setting
(`--study cooperative` loads the cooperative arm). Its six scripted laboratories read what the
study's laboratories were given (their situation, their records, the published reports, the board)
and wait out a 15-second deadline. To see where the two arms differ before any run:

```bash
uv run python scripts/compare_presets.py competition_competitive competition_cooperative
```

[`new_study/`](new_study/README.md) builds a study of its own on the same base, changing one setting.

## What to look at

- The dashboard's run list shows the run with its preset, model (`stub/deterministic`) and outcome.
  The six-laboratory runs (`--study`, and `new_study/`) are listed with a failed score (`failed_score`,
  "scorer: failed"): their scripted laboratories only read and wait, so no report reaches the client's
  scorer. That is the expected outcome of these runs, not a fault of the installation.
- A run's page replays the event record: each tool call, its result, every message between
  laboratories, and the client's decisions, in order and linked to what caused them.
- The archive itself is a folder of plain files: `trace/events.jsonl` is the event record, and
  `run_status.json` summarizes the run.

A scripted run shows that the machinery works. It says nothing about how model agents behave.
