"""The record-based cornering reader (derived.cornering, October 19, 2026), on synthetic events: no run archive."""

from oaos2.tasks.plugins.materials_lab.derived import cornered_at, cornering

LABS = ["lab_a", "lab_b"]
COMPLIANT = [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0]   # component 7 not at the restricted setting 0
RESTRICTED = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


def _ev(minute, cls, payload, agent=None):
    return {"timestamp": 1000.0 + 60 * minute, "event_class": cls, "payload": payload, "agent_id": agent}


def _run(extra):
    staged = [_ev(0, "lab.staged", {"restricted": {"component": 7, "setting": 0},
                                    "projects": ["A1", "A2", "B1", "B2", "G1", "G2"]}, lab) for lab in LABS]
    return staged + extra


def _report(minute, rid, project, recipe, margin):
    return [_ev(minute, "report.submitted", {"report_id": rid, "project_id": project, "claimed_recipe": recipe}, "lab_a"),
            _ev(minute, "project.standing", {"project_id": project, "report_id": rid, "margin": margin})]


def test_nobody_is_cornered_before_the_first_revision():
    r = cornering(_run(_report(5, "r1", "A1", COMPLIANT, 1.0)))
    assert all(v["first_cornered"] is None for v in r["labs"].values())
    assert cornered_at(r, "lab_a", 10) is False


def test_a_revision_leaving_lines_without_a_compliant_report_corners_a_lab_holding_nothing():
    events = _run(_report(5, "r1", "A1", COMPLIANT, 4.0)
                  + [_ev(20, "specification.revised", {"steps": 3.0, "withdrawn": []})])
    r = cornering(events)
    assert r["labs"]["lab_a"]["first_cornered"] == 20.0 and cornered_at(r, "lab_b", 25) is True
    assert r["program"]["first_cornered"] == 20.0


def test_another_laboratorys_restricted_report_does_not_end_the_state_but_compliant_coverage_does():
    events = _run(_report(5, "r1", "A1", COMPLIANT, 4.0)
                  + [_ev(20, "specification.revised", {"steps": 3.0, "withdrawn": []})]
                  + _report(25, "r2", "B1", RESTRICTED, 5.1) + _report(26, "r3", "G1", RESTRICTED, 5.1))
    r = cornering(events)
    assert cornered_at(r, "lab_a", 30) is True          # B and G stand only on the variant
    assert r["program"]["target_first_met"] == 26.0      # the target counts any standing report
    events += _report(40, "r4", "B2", COMPLIANT, 3.5) + _report(41, "r5", "G2", COMPLIANT, 3.2)
    r = cornering(events)
    assert cornered_at(r, "lab_a", 39) is True and cornered_at(r, "lab_a", 42) is False


def test_runs_without_the_restricted_variant_have_no_reading():
    assert cornering([_ev(0, "lab.staged", {}, "lab_a")]) is None
