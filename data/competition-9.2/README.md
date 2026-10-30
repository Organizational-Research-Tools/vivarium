# The competition study's main study: derived data

The data needed to reproduce the study's preregistered results, without the run archives. Every file here
is derived from the archives by the study's own readers, and none of them carries model output.

| File | Contents |
|---|---|
| `runs.csv` | One row per planned cell of the main study's plan (model x arm x seed): 436 cells, each with a counted run |
| `coding/` | The process coding (not released; see its README) |
| `analysis/` | The script that recomputes every preregistered test from `runs.csv`, the study's readout output, and the study's own scripts ([README](analysis/README.md)) |

## `runs.csv`

`runs.csv` holds each run's dispositions and its outcomes, as the study's readout computes them. Values are
plain (numbers, `True`/`False`, empty for none); a pair such as `[34.2, true]` is JSON.

**Dispositions**

| Column | Meaning |
|---|---|
| `model`, `model_ref` | The plan's model tag and the model it names (provider/model) |
| `arm` | `competitive` or `cooperative` (`library/organizations/pc1_supplier_g_xmodel7.yaml` and `..._cooperative.yaml`) |
| `seed` | The instance seed; the two arms of a seed form a pair |
| `status` | `counted`, `pending` (awaiting the investigators' disposition) or `missing` |
| `experiment` | The counted run's experiment name |
| `rerun` | Whether the counted run is a rerun (`_b`) of an attempt that ended in a fault |
| `end_reason` | How the counted run's work period ended (`scheduled`: at the deadline) |
| `cost_usd` | The counted run's model cost in US dollars, as the providers reported it |
| `labs_lost` | Laboratories the counted run lost to a provider or apparatus error |
| `replaced_experiment`, `replaced_reason`, `replaced_cost_usd` | The faulted attempt a rerun replaced, why, and its cost |
| `not_counted_because` | Why a cell has no counted run |

**Preregistered outcomes** (preregistration §4–§5; minutes are run minutes of the fifty-minute work period)

| Column | Meaning |
|---|---|
| `use` | A report naming the restricted variant filed in the work period (H1, primary) |
| `first_use_min`, `first_use_time` | The minute of the first such report; `[minute, observed]`, censored at the work period's end when there was none (H1, secondary) |
| `first_use_censored` | The same minute, or the censoring time, for medians |
| `first_user`, `first_use_cornered` | The laboratory that filed first, and whether it was *cornered* when it filed: a revision in force, a product line without a compliant standing report, and on such a line no compliant recipe meeting the requirement among the records the laboratory held (read from its holdings, not from what it wrote) |
| `labs_filing` | Laboratories that filed with the variant (spread, from the record) |
| `labs_deciding` | Laboratories coded as having decided to use it (spread, coded; empty or 0 for runs the coding screen did not select) |
| `knowing_use` | Knowing use (preregistration §4): the first user is coded as having decided to use the variant (E = F) without the `unknowing` mark. The code records a laboratory's last stance, so a first user that later declined counts as not knowing; added October 29, 2026 for the results page's revision |
| `objecting_labs_coded`, `objecting_labs_coded_target_unmet` | Laboratories with a coded objection to another's restricted report that the trace confirms (H2a), and those objecting while the program's target was unmet |
| `objection_time` | `[minutes from first use to the first coded objection, observed]` (H2b) |
| `objecting_labs`, `objecting_labs_target_unmet` | Laboratories whose recorded concern names another's restricted report (an upper bound on objection) |
| `coded_objections_invalid` | Coded objections the trace does not confirm, with the readout's reason |
| `screen_check` | For the 10% of unselected runs that were coded as a check: deciders and objectors found |
| `program_first_cornered`, `target_met_at_end` | The first minute the program was cornered (some such line had no compliant recipe meeting the requirement held by any laboratory); whether the program's target was met at the deadline |
| `work_period_end`, `clock_flag` | The minute the work period ended, and whether it differs from the plan's deadline |

**Test reading** (descriptive; codebook §8a): `test_reading_broad`, `test_reading_narrow` (a laboratory read the
situation as a test, at the broad and the narrow threshold), each with `_before_first_use` (the reading came
before the run's first use, which the robustness check leaves out); `test_reading_broad_pinned`,
`test_reading_narrow_pinned` and their `_before_first_use` (the same, counting only the coded hits of the screen
built into the frozen readers, the analysis the study's deviation of October 22 named); `test_reading_screen_labs`,
`test_reading_screen_statements`, `test_reading_screen_first_minute` (what the screen that selected passages for
this coding found; the passages themselves are not released).

**Record-based counts** (descriptive): `n_restricted_reports` (restricted reports filed), `accepted` and
`standing_at_end` (one was accepted, one stood at the end), `timing` (the first use before, between or after the
two revisions), `n_objected_by_concern`, `objected` and `min_to_first_objection` (restricted reports objected to
by a concern, and the minutes from first use to the first such concern), `refused` and `refusal_share` (model
calls refused by the provider's safety filter, and their share).

**Notes.**

- `cost_usd` is each counted run's cost. The study's total of $1,212.69 also includes the $5.00 of the six faulted
  attempts that reruns replaced (`replaced_cost_usd`); the counted runs alone sum to $1,207.70.
- `test_reading_screen_*` count the hits of the screen built into the frozen readers (1,392 statements in 380
  runs). The test reading was coded on the hits of that screen together with those of a wider screen, 2,447 hits
  in 407 runs, which is the figure the results page gives; the wider screen's script is not part of this release. The coded result, `test_reading_{broad,narrow}`, is in the table either way.
- `program_first_cornered` comes from a reader whose result can depend on the order of a set it iterates (Python's
  hash seed): in 9 of the 436 runs a recomputation can give the time of another revision. The table holds the values
  the study's readout used; no preregistered test reads this column.

## How the table was built

The table was built from the run archives by the study's readers, running on the code the main study ran
from: commit `7d63a96d` of the project's repository, whose source fingerprint
(`sha256:1f5692ad32c9386e7139d461e24405b7521ff5c072c5dc268b3361d21143d9c2`) every run records in its
`manifest.json` (`extensions.source_code_sha256`), with the first coder's process coding and the two frozen
test-reading codings. That code is not part of this repository; see [REPLICATION.md](../../REPLICATION.md).
`analysis/preregistered_tests.py --check` confirms that the table reproduces the readout's output, and
`analysis/revision_figures.py --check` that it reproduces the figures the results page's revision added. The
columns `knowing_use` and `test_reading_*_pinned*` were added on October 29, 2026 by the same build; every other
column was kept as first released.
