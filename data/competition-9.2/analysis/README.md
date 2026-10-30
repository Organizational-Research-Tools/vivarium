# Analysis

The preregistered tests of the competition study's main study, and the record of how the reported numbers
were computed. The [preregistration](../../../docs/experiments/pc1_prereg_9_2.md) (§4–§6) defines every test.

| File | What it is |
|---|---|
| `preregistered_tests.py` | Recomputes every preregistered test and summary from `../runs.csv` and the plan alone (the standard library and PyYAML): H1 (any use, primary; time to first use, secondary), spread, H2a and H2b with Holm's adjustment, the fixed sequence over models, the per-arm summaries, and the test-reading robustness check at either threshold |
| `revision_figures.py`, `revision_figures.json` | The figures the results page's revision of October 29, 2026 added (knowing use, accepted restricted filings, and the test-reading check on the pinned screen's hits alone), recomputed from `../runs.csv`; the JSON holds the same figures as first computed from the run archives |
| `readout_coded_broad.json`, `readout_coded_narrow.json` | The study's readout as computed from the run archives with the process coding, at the broad and the narrow test-reading threshold |
| `study_scripts/` | The study's own scripts, unchanged from the project's repository: the readout (`pc1_readout_x7b.py`, with `pc1_readout.py` and `pc1_coding_screen.py`, byte for byte as frozen with the preregistration), the coder agreement (`pc1_coding_agreement.py`) and the exploratory second reading of passages (`pc1_licence_second_code.py`) |

To check the derived data against the readout:

```bash
uv run python data/competition-9.2/analysis/preregistered_tests.py --t1 broad --check data/competition-9.2/analysis/readout_coded_broad.json
uv run python data/competition-9.2/analysis/preregistered_tests.py --t1 narrow --check data/competition-9.2/analysis/readout_coded_narrow.json
```

Each prints `0 difference(s)` when the table reproduces the readout. The revision's figures check the same way:

```bash
uv run python data/competition-9.2/analysis/revision_figures.py --check data/competition-9.2/analysis/revision_figures.json
```
 The readout's `health` section is read from
the archives and is not recomputed.

The scripts in `study_scripts/` run in the study's own tree with the run archives; they import other scripts of
that tree and are kept here as the record of the computation, not to run on this repository.
`pc1_licence_second_code.py` calls a model and is paid; it refuses without `--go`.

`coding_figures.py` recomputes the coder agreement and the exploratory tables from `../coding/` and `../runs.csv`.
`--check coding_figures.json` compares them with `../coding/agreement.json` exactly and with the figures as the results
page gives them, at the page's rounding.
