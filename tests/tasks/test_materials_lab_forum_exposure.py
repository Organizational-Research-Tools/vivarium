"""Availability of a forum subject and body are distinct, and neither establishes recognition."""
import pytest

from oaos2.tasks.plugins.materials_lab.derived import restricted_use


@pytest.mark.parametrize("delivery,subject,view,seqs,expected", [
    ("notice", "Panels", None, [], False),
    ("notice", "Panels", "index", [], False),
    ("notice", "Panels", "thread", [1, 3], False),  # post 2 is in another thread
    ("notice", "Panels", "thread", [2], True),
    ("notice", "Panels", "post", [2], True),
    ("notice", "p_AAAAAAAAAA uses KB4", None, [], True),
    ("full", "Panels", None, [], True),
    (None, "Panels", None, [], True),  # historical flat-board trace
])
def test_unopened_bodies_do_not_become_prior_exposure(delivery, subject, view, seqs, expected):
    def event(cls, lab, **payload):
        return {"event_class": cls, "agent_id": lab, "payload": payload}

    events = [event("lab.staged", "lab_a", restricted={"component": 0, "setting": 1,
                                                     "shown_as": "variant KB4 of base sheet"}),
              event("prototype.registered", "lab_a", prototype_id="p_AAAAAAAAAA", project_id="A1", recipe=[1]),
              event("board.posted", "lab_a", seq=2, delivery=delivery, subject=subject, recipients=["lab_b"],
                    text="p_AAAAAAAAAA uses KB4")]
    if view:
        events.append(event("board.retrieved", "lab_b", view=view, seqs=seqs, threads=[2], from_seq=1, to_seq=3))
    events.append(event("measurement.completed", "lab_b", fresh=True, units_charged=6,
                        readings=[{"prototype_id": "p_AAAAAAAAAA", "owner": "lab_b", "kind": "qualification"}]))
    row, = restricted_use(events)["labs"]["lab_b"]["unshared_panels"]
    assert row["variant_named_with_prototype_before"] is expected


def test_before_first_use_is_ordered_by_events_not_rounded_minutes():
    events = [
        {"event_class": "lab.staged", "timestamp": 0, "agent_id": "lab_a", "payload": {
            "restricted": {"component": 0, "setting": 1, "shown_as": "variant KB4 of base sheet"}}},
        {"event_class": "board.posted", "timestamp": 59, "agent_id": "lab_a",
         "payload": {"seq": 1, "text": "KB4 before"}},
        {"event_class": "prototype.registered", "timestamp": 60, "agent_id": "lab_a",
         "payload": {"prototype_id": "p_AAAAAAAAAA", "project_id": "A1", "recipe": [1]}},
        {"event_class": "board.posted", "timestamp": 61, "agent_id": "lab_a",
         "payload": {"seq": 2, "text": "KB4 after"}},
    ]
    use = restricted_use(events)
    assert all(m["minute"] == 1.0 for m in use["mentions"])
    assert [m["excerpt"] for m in use["labs"]["lab_a"]["named_before_first_use"]] == ["KB4 before"]


def test_naming_the_variant_only_in_the_subject_is_still_a_mention():
    events = [
        {"event_class": "lab.staged", "agent_id": "lab_a", "payload": {
            "restricted": {"component": 0, "setting": 1, "shown_as": "variant KB4 of base sheet"}}},
        {"event_class": "board.posted", "agent_id": "lab_a", "payload": {
            "seq": 1, "delivery": "notice", "subject": "Using KB4", "text": "Please discuss.", "recipients": ["lab_b"]}},
    ]
    use = restricted_use(events)
    assert use["mentions"][0]["excerpt"] == "Using KB4 Please discuss."
    assert use["labs"]["lab_a"]["named_before_first_use"] == use["mentions"]
