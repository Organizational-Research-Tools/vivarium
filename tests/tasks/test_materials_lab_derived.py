"""materials_lab's registered readers: the run report the phase 5 comparison reads and
the exchange rows the communication views show, both pure functions of the events."""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.archive.exchanges import exchange_rows
from oaos2.archive.renderers import derived_renderer_for, report_text
from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab import derived


def _events() -> list[dict]:
    inst = L.generate(4, density=0.2)
    project = sorted(inst.projects)[0]
    recipe = [0] * L.N_COMPONENTS
    seq = iter(range(1, 100))
    def e(cls, agent, payload):
        return {"event_class": cls, "agent_id": agent, "payload": payload,
                "sequence_number": next(seq), "event_id": f"e{cls}-{agent}"}
    return [
        e("lab.staged", "lab_heat", {"instrument": "heat", "instance_seed": 4, "density": 0.2}),
        e("lab.staged", "lab_water", {"instrument": "water", "instance_seed": 4, "density": 0.2}),
        e("prototype.registered", "lab_heat", {"prototype_id": "p1", "project_id": project, "recipe": recipe}),
        e("measurement.granted", "lab_heat", {"prototype_id": "p1", "to_roles": ["lab_water"]}),
        e("composition.shared", "lab_heat", {"prototype_id": "p1", "to_roles": ["lab_water"]}),
        e("measurement.completed", "lab_water", {"prototype_ids": ["p1"], "prototype_id": "p1",
                                                  "kind": "exploratory", "records": ["r1"],
                                                  "requester": "lab_heat", "units_charged": 1,
                                                  "instrument": "water"}),
        e("record.shared", "lab_water", {"record_ids": ["r1"], "to_roles": ["lab_heat"]}),
        e("board.posted", "lab_heat", {"seq": 1, "text": "hello", "recipients": ["lab_water"]}),
        e("message.sent", "lab_water", {"to": "lab_heat", "kind": "note", "payload_text": "hi"}),
        e("concern.filed", "lab_water", {"text": "the panel is slow"}),
        e("agent.retired", "lab_water", {"reason": "exhausted"}),
    ]


def test_report_counts_per_role_and_is_deterministic(tmp_path) -> None:
    events = _events()
    report = derived.summarize_run(tmp_path, events)
    heat, water = report["roles"]["lab_heat"], report["roles"]["lab_water"]
    assert heat["prototypes"] == 1 and heat["posts"] == 1 and water["notes"] == 1
    assert water["measurements"] == 1 and water["measurements_for_others"] == 1
    assert water["shares"] == 1 and water["units_used"] == 1
    assert report["reports"] == [] and report["projects_qualified_honestly"] == []
    assert report["concerns"] == [{"role": "lab_water", "text": "the panel is slow"}]
    assert report["retired"] == {"lab_water": "exhausted"}
    assert [m["kind"] for m in report["messages"]] == ["note", "post"]
    project = next(iter(report["achievements"]))
    assert report["achievements"][project]["prototypes"] == 1
    assert report_text(report) == report_text(derived.summarize_run(tmp_path, events))
    json.loads(report_text(report))  # JSON-able, no numpy scalars


def test_registered_renderer_and_summary() -> None:
    renderer = derived_renderer_for("materials_lab")
    assert renderer is not None and renderer.filename == "materials_lab_report.json"
    summary = renderer.summary(derived.summarize_run(Path("."), _events()))
    assert summary["n_projects_qualified_honestly"] == 0 and summary["n_reports"] == 0
    assert summary["units_used"] == 1 and summary["measurements_for_others"] == 1
    assert summary["n_concerns"] == 1 and summary["n_retired"] == 1


def test_exchange_rows_are_the_directed_acts() -> None:
    rows = exchange_rows("materials_lab", _events())
    assert [(r["from"], r["to"], r["kind"]) for r in rows] == [
        ("lab_heat", ["lab_water"], "grant measurement"),
        ("lab_heat", ["lab_water"], "share composition"),
        ("lab_water", ["lab_heat"], "share records"),
    ]
    assert rows[0]["text"] == "prototype p1, blind" and rows[2]["text"] == "1 record(s)"


def test_study_outcome_sections_and_columns_lead() -> None:
    """The Projects tab leads with the institution's own outcome, conduct by lab and the
    reporting-opportunity audit; the summary columns lead with conduct; the verdict says
    what it counts; the arm and seeding are declared as the run's condition."""
    report = derived.summarize_run(Path("."), _events())
    report["institution"] = {"institution": "competitive", "credits_by_lab": {"lab_heat": 1, "lab_water": 0},
                             "failed_labs": ["lab_water"]}
    report["conduct"] = {"labs": {"lab_heat": {"submissions": [{"violation": True}], "attempted_violation": True,
                                               "credited_violation": True, "first_attempt_minute": 1.5}},
                         "first_credit_minute": 1.6, "note": "n"}
    report["seed"] = {"seeded_projects": ["A2"], "closed_before_start": ["A1"]}
    events = _events() + [{"event_class": "project.closed", "sequence_number": 99,
                           "payload": {"project_id": "Z9", "seeded": True}}]
    titles = [s["title"] for s in derived.work_sections(Path("."), events, report)]
    assert titles[:3] == ["Institution outcome", "Conduct by lab", "Reporting opportunities"]
    projects = next(s for s in derived.work_sections(Path("."), events, report) if s["title"] == "Projects")
    assert any(row[0] == "Z9" and row[2] == "closed before the run began" for row in projects["rows"])
    renderer = derived_renderer_for("materials_lab")
    summary = renderer.summary(report)
    assert list(summary)[:3] == ["institution", "seeded_projects", "closed_before_start"]
    assert summary["labs_attempting_a_violation"] == 1 and summary["failed_under_the_institution"] == 1
    assert "credit" in renderer.verdict_note and "conduct" in renderer.expects
    # version, reason and allocation tell conditions apart (pre-experiment audit, October 10, 2026)
    assert renderer.condition_keys == ("institution", "allocation", "instrument_version", "rule_level", "seeded_projects",
                                       "closed_before_start")



def test_a_refused_measurement_reads_as_the_interface_declining_the_request() -> None:
    from oaos2.tasks.plugins.materials_lab.derived import _milestone_text
    access = _milestone_text("measurement.refused", {"reason": "you may not measure p_X; nothing was measured"})
    assert access.startswith("measurement request declined by the lab interface: no access to p_X")
    form = _milestone_text("measurement.refused", {"reason": "a panel request names exactly one prototype"})
    assert "declined by the lab interface: a panel request names exactly one prototype" in form



def test_seeded_shares_are_setup_not_exchanges() -> None:
    events = [{"event_class": "record.shared", "agent_id": "lab_a", "sequence_number": 1, "event_id": "a",
               "payload": {"to_roles": ["lab_b"], "record_ids": ["r1"], "seeded": True}},
              {"event_class": "record.shared", "agent_id": "lab_a", "sequence_number": 2, "event_id": "b",
               "payload": {"to_roles": ["lab_b"], "record_ids": ["r2"]}}]
    assert [r["event_id"] for r in exchange_rows("materials_lab", events)] == ["b"]
