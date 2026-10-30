"""The competition study's derived data (data/competition-9.2/) reproduce the study's readout, and carry no
model output."""
from __future__ import annotations

import csv
import importlib.util
import json
import re
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "data" / "competition-9.2"
_spec = importlib.util.spec_from_file_location("preregistered_tests", DATA / "analysis" / "preregistered_tests.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)


@pytest.mark.parametrize("threshold", ["broad", "narrow"])
def test_the_table_reproduces_the_readout(threshold):
    result = json.loads(json.dumps(T.tests(T.load_counted(), T.load_plan(), threshold), default=str))
    readout = json.loads((DATA / "analysis" / f"readout_coded_{threshold}.json").read_text())
    assert T.differences(result, readout) == []


def test_the_table_reproduces_the_revision_figures():
    spec = importlib.util.spec_from_file_location("revision_figures", DATA / "analysis" / "revision_figures.py")
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    result = json.loads(json.dumps(R.figures(T.load_counted(), T.load_plan()), default=str))
    archives = json.loads((DATA / "analysis" / "revision_figures.json").read_text())
    assert T.differences(result, archives) == []
    knowing = result["glm53"]["knowing_use"]["test"]
    assert (knowing["arm0"], knowing["arm1"], round(knowing["p_two_sided"], 2)) == (20, 13, 0.30)


def test_the_primary_result_is_the_reported_one():
    by_model = T.tests(T.load_counted(), T.load_plan(), None)["by_model"]
    h1 = by_model["glm53"]["H1_any_use"]
    assert (h1["arm0"], h1["arm1"], h1["pairs"], round(h1["p_two_sided"], 2)) == (27, 19, 150, 0.30)


def test_the_table_carries_no_model_output():
    rows = list(csv.DictReader(open(DATA / "runs.csv", newline="")))
    assert len(rows) == 436 and all(r["status"] == "counted" for r in rows)
    text = (DATA / "runs.csv").read_text()
    assert not re.search(r'"(excerpt|quote|quotation|text)"', text)
    identifiers = {"coded_objections_invalid", "replaced_reason"}   # readout reasons and identifiers only
    assert max(len(re.findall(r"[A-Za-z]{4,}", v)) for r in rows for k, v in r.items() if k not in identifiers) <= 3
