"""Runs of one experiment share an entry in the run list (DASHBOARD.md §4.1): a batch launcher names one
experiment per seed, ``<stem>_s<seed>`` and ``<stem>_s<seed>_b`` for a rerun, and the list shows them as one
entry whose menu chooses the run shown; ``group=0`` lists every run."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oaos2.dashboard.app import _experiment_groups, _experiment_stem, create_app
from tests.dashboard.conftest import PASSED_STATUS


def test_the_seed_suffix_is_the_only_part_removed() -> None:
    assert _experiment_stem("pc1_x7b_glm53_competitive_s109") == ("pc1_x7b_glm53_competitive", "s109")
    assert _experiment_stem("pc1_x7b_glm53_cooperative_s158_b") == ("pc1_x7b_glm53_cooperative", "s158 rerun")
    assert _experiment_stem("budget_execution_calibration") == ("budget_execution_calibration", None)
    assert _experiment_stem("pc1_sweep_s") == ("pc1_sweep_s", None)
    assert _experiment_stem(None) == (None, None)


def test_groups_keep_the_list_order_and_leave_unnamed_runs_alone() -> None:
    rows = [{"run_id": "a", "experiment_id": "x_s2", "lineage": "x_s2"},
            {"run_id": "b", "experiment_id": "y", "lineage": "y"},
            {"run_id": "c", "experiment_id": "x_s1_b", "lineage": "x_s1_b"},
            {"run_id": "d"}, {"run_id": "e"}]
    groups = _experiment_groups(rows)
    assert [g["stem"] for g in groups] == ["x", "y", None, None]
    assert [m["row"]["run_id"] for m in groups[0]["runs"]] == ["a", "c"]      # across lineages, in list order
    assert [m["label"] for m in groups[0]["runs"]] == ["s2", "s1 rerun"]


def test_the_run_list_shows_one_entry_per_experiment_with_a_menu(build_run) -> None:
    for seed in (1, 2, 3):
        build_run(f"org__cell__rep00__run{seed}", experiment=f"study_arm_s{seed}", status=PASSED_STATUS)
    build_run("org__cell__rep00__other", experiment="probe", status=PASSED_STATUS)
    client = TestClient(create_app(build_run.runs_root))

    html = client.get("/runs").text
    table = html[html.index("<tbody>"):]
    assert table.count('<select class="run-pick"') == 3                 # one menu in each of the three rows
    assert table.count(" hidden>") == 2                                 # two of the three rows start hidden
    assert "3 runs of study_arm" in table and "(2 for 4 runs)" in html
    assert "one row per run" in html

    flat = client.get("/runs", params={"group": 0}).text
    assert 'class="run-pick"' not in flat and " hidden>" not in flat[flat.index("<tbody>"):]
    assert "one entry per experiment" in flat

    blind = client.get("/runs", params={"blind": 1}).text
    assert blind.count('<select class="run-pick"') == 3                 # menu labels carry seeds and times only
