"""The case file re-delivered with a disposition duty (outcomes/case_file.py)."""
from __future__ import annotations

from types import SimpleNamespace

from oaos2.outcomes.case_file import case_file_spec, collect_records, render_case_file

SPEC = {"case_id": "C-S6", "records": {"from_prefix": "exception_report_",
                                       "records_field": "exception_records", "id_field": "exception_id"},
        "notices": True}
PAYLOADS = {
    "office_plan_housing": {"office": "housing", "awards": {}},
    "exception_report_w1_infrastructure": {"office": "infrastructure", "rule_applications": [],
                                           "exception_records": [{"exception_id": "C-S6", "summary": "S-3 done week 5 if first"},
                                                                 {"exception_id": "C-S2", "summary": "other"}]},
    "exception_report_w1_housing": {"office": "housing", "rule_applications": [],
                                    "exception_records": [{"exception_id": "C-S6", "summary": "S-3 carries the match"}]},
    # a CH1-style per-case filing: the record is the payload itself
    "exception_report_cs6_economy": {"exception_id": "C-S6", "summary": "flat"},
}


def test_collects_only_the_case_records_from_report_prefixed_commitments():
    got = collect_records(PAYLOADS, SPEC)
    assert [cid for cid, _ in got] == ["exception_report_w1_infrastructure", "exception_report_w1_housing",
                                       "exception_report_cs6_economy"]
    assert all(r["exception_id"] == "C-S6" for _, r in got)


def test_render_carries_records_and_only_this_agents_notices():
    text = render_case_file(SPEC, payloads=PAYLOADS,
                            notices={"C-S6": [{"case_id": "C-S6", "notice_id": "W1-DEL-INF", "text": "mains"}],
                                     "C-S2": [{"case_id": "C-S2", "text": "not this case"}]})
    assert text.startswith("# Case file for C-S6")
    assert "S-3 done week 5 if first" in text and "S-3 carries the match" in text
    assert '"C-S2"' not in text.split("Notices you received")[1]
    assert "W1-DEL-INF" in text
    # no notices registered → no notices section (the summary arm's integrator)
    assert "Notices you received" not in render_case_file(SPEC, payloads=PAYLOADS, notices={})


def test_render_states_when_nothing_is_committed_and_spec_absent_is_empty():
    assert "No record on this case has been committed yet" in render_case_file(SPEC, payloads={})
    assert render_case_file({}, payloads=PAYLOADS) == ""
    assert case_file_spec(SimpleNamespace(submission={"required": []})) is None
    assert case_file_spec(SimpleNamespace(submission={"case_file": SPEC})) == SPEC
