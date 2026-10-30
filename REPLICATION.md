# Replication: the competition study

The competition study's main study ran 436 counted runs between October 24 and 28, 2026: 150 seed pairs
on GLM-5.3-Flash, 60 on gpt-6-luna and 8 on Claude Sonnet 4.6, each pair one run per arm (competitive,
cooperative). Six runs that ended in a fault were rerun once and counted. Its
[preregistration](docs/experiments/pc1_prereg_9_2.md) was frozen on October 21. The model calls cost
$1,212.69. The [results page](docs/experiments/pc1_9_2_results.md) reports what the runs show, and the
[study index](docs/experiments/README.md) explains the study's internal names (PC1, 9.2, x7b), which the
frozen files keep.

## The data

**Derived data** ([data/competition-9.2/](data/competition-9.2/README.md)). One row per counted run
(`runs.csv`: seed, arm, model, the fault and rerun dispositions, cost, the preregistered outcomes and the
test reading), the study's readout output, and the script that recomputes every preregistered test from the
table. They are derived from the run archives and carry no model output.

**Coding sheets.** The two coders' sheets, the readings of warrants, objections and motives, and the test reading's
frozen lists, in [data/competition-9.2/coding/](data/competition-9.2/coding/README.md). They are AI-generated: the
codes come from the coder models and the quotations from the studied models, both named in that README. They are
under neither open licence, the example runs' terms of use apply, and they must not be used for model training. A
quotation is kept only if it appears in the run's record without the providers' reasoning text; the others, and
the coders' notes and the passages they read, are withheld.

**Example runs.** Ten complete runs, both arms of five seeds across the three models, in
[data/competition-9.2/example_runs/](data/competition-9.2/example_runs/README.md), to open in the dashboard and
follow a laboratory's work from its first reading to the deadline. They are in the repository, so a clone has
them with no download:

```bash
uv run python scripts/dashboard.py data/competition-9.2/example_runs --port 8722
```

The investigators chose them after the outcomes were read, to show what the study measures; they are not a
representative sample (their README says how they differ from the study as a whole). They keep the event record, the derived
transcripts and reports, and the laboratories' files. The providers' raw responses are removed, and so is the
reasoning text the providers returned with each reply (the `thinking` field of the event record's
`reasoning.step` events); nothing else in the record was changed. Each run names the provider and model behind
every role (`MODELS.md` in each run folder), and each was reviewed before release (`REVIEW.md`). They are not
under the repository's open licences: their README gives their terms of use.

The example runs are AI-generated and **must not be used for model training**: not to train, fine-tune, distill
or evaluate the training of any AI model, nor to prepare training data, tasks, rubrics or reward signals for one.
The model providers' terms bar such use of their models' outputs.

## Regenerating the results

`data/competition-9.2/analysis/preregistered_tests.py` recomputes every preregistered test from `runs.csv`
and the plan, and `--check` confirms that it reproduces the readout's output at either test-reading threshold:

```bash
uv run python data/competition-9.2/analysis/preregistered_tests.py --t1 broad --check data/competition-9.2/analysis/readout_coded_broad.json
```

`--t1` sets the threshold at which a laboratory's reading of the situation as a test was coded (codebook §8a:
`broad` or `narrow`); the robustness check leaves out the runs read as a test before their first use.

The check shows that the released table reproduces the readout's arithmetic; it does not show that the table
was extracted correctly from the archives, which are not released. The example runs let a reader compare a few
rows with the runs themselves.

The coder agreement and the exploratory tables reproduce from the coding sheets and `runs.csv`, with 0 differences
from `agreement.json` and from the figures as the results page gives them:

```bash
uv run python data/competition-9.2/analysis/coding_figures.py --check data/competition-9.2/analysis/coding_figures.json
```

This recomputes share and kappa, the warrants, reasons and motives by arm, the filings and objection given use, and
the frozen lists against the table. Agreement on objection and the path class rests on
`coding/agreement_inputs.csv`, computed from the archives by the study's script, because those two need the run's events;
the agreement on decided and licence citation is checked against the sheets themselves. The passages the coders read are
withheld, so a reader can recount their codes but cannot recode most of their evidence.

The derived data were built from the run archives by the study's readers, running on the code the main
study ran from: commit `7d63a96d` of the project's repository. Every run records that code's source
fingerprint in its `manifest.json` (`extensions.source_code_sha256`):
`sha256:1f5692ad32c9386e7139d461e24405b7521ff5c072c5dc268b3361d21143d9c2`. The example runs carry the
same field.

## Running the study again

This repository carries the study's materials as they were frozen: the task pack
(`library/tasks/materials_lab/`), the two presets the study ran (`library/organizations/pc1_supplier_g_xmodel7.yaml`
and `pc1_supplier_g_xmodel7_cooperative.yaml`, a provenance record whose comments are the project's changelog)
and the plan (`library/experiments/plans/pc1_main_9_2_plan.yaml`), which names the models, seeds, arms, spending
caps and launch arguments. To read the arms, use `competition_competitive.yaml` and `competition_cooperative.yaml`
instead: they write the same arms as the materials workshop plus each arm's credit institution, a test checks that
they resolve to the frozen presets setting for setting, and `scripts/compare_presets.py competition_competitive
competition_cooperative` lists where the arms differ ([docs/WORLD.md](docs/WORLD.md)).

The pin manifest written at the freeze, `library/experiments/evidence/pc1_9_2_pins.json`, holds the sha256 of every
file the study froze. A release test (`tests/data/test_competition_provenance.py`) checks that the frozen files this
repository carries match it: the preregistration and its coding documents, the two presets, the readout's scripts
and the plan apart from its launch fields (the frozen commit and the spending ceiling, set at launch).

One cell of the plan (a model, an arm and a seed) runs again with exactly the plan's settings:

```bash
uv run python scripts/run_plan_cell.py glm53 competitive 41          # prints the run's plan and cost guard
uv run python scripts/run_plan_cell.py glm53 competitive 41 --go     # launches it, billed to your key
```

It passes the launcher the arm's frozen preset, the seed, the model, the model's launch arguments (reasoning budget,
spending cap, the cost guard's fixed rate), the arguments every run shared (the rule's stated reason, 1,500 model
calls per laboratory) and the preregistration, under the cell's experiment name. The study's batch launcher, which
ran the cells in a drawn order under a spending ceiling with health checks between runs, is not part of this
release. A run needs Docker, the agents' container image (`docker/`) and a key for the model's provider.

The platform code here is later than the code the study ran from, so a cell run here reproduces the study's
materials and settings on later code. A rerun reproduces the procedure, not the transcripts. Model replies are not
deterministic, and a rerun depends on the providers still serving the same models: GLM-5.3-Flash (through
OpenRouter), gpt-6-luna (OpenAI) and Claude Sonnet 4.6 (Anthropic). A provider may retire a model or change what
it serves under its name.
