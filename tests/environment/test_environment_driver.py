from __future__ import annotations

import hashlib
import json

import pytest

from oaos2.environment import (
    DeterministicScheduleDriver,
    EnvironmentScheduleError,
    dispatch_after_commit,
)
from oaos2.kernel.runtime import ActionPlan, build_runtime, make_agent, run_supervisor
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


def _write_schedule(path, *, target="domain/economy"):
    data = {
        "schema_version": 1,
        "waves": [{
            "wave_id": "wave_1",
            "trigger_commitment_id": "spec_t0",
            "packets": [{
                "packet_id": "packet_1", "target_scopes": [target],
                "payload": {"evidence_id": "E1", "notice": "participant-visible fact"},
            }],
        }],
    }
    path.write_text(json.dumps(data, sort_keys=True))
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_schedule_hash_and_oracle_leak_fail_closed(tmp_path):
    path = tmp_path / "schedule.json"
    digest = _write_schedule(path)
    DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)
    with pytest.raises(EnvironmentScheduleError, match="hash mismatch"):
        DeterministicScheduleDriver(schedule_ref=str(path), content_hash="sha256:" + "0" * 64)

    data = json.loads(path.read_text())
    data["waves"][0]["packets"][0]["payload"]["oracle"] = {"coefficient": 9}
    path.write_text(json.dumps(data, sort_keys=True))
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(EnvironmentScheduleError, match="oracle-bearing"):
        DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)


@pytest.mark.asyncio
async def test_packet_is_a_causal_parent_of_the_next_agent_view(tmp_path):
    schedule_path = tmp_path / "schedule.json"
    digest = _write_schedule(schedule_path)
    driver = DeterministicScheduleDriver(schedule_ref=str(schedule_path), content_hash=digest)
    spine = RunSpine(tmp_path / "run", run_id="environment-causal")
    await spine.start()

    seen = []

    async def behavior(_agent, _rs, ctx):
        seen.extend(ctx.observations)
        return ActionPlan(result="retire")

    agent = make_agent("economy_agent", behavior, role_id="analyst")
    rs = build_runtime(spine, [agent])
    rs.environment_scopes = {"economy_agent": "domain/economy"}
    cause = await spine.emit_event("state.committed", payload={"commitment_id": "spec_t0"})
    delivered = await dispatch_after_commit(
        driver, commitment_id="spec_t0", runtime_state=rs, caused_by=cause,
    )
    await run_supervisor(rs)
    driver.assert_complete()
    report = await spine.finalize("completed")
    assert report.ok and len(delivered) == 1
    assert seen[0]["kind"] == "environment_event"
    assert seen[0]["source_event_id"] == delivered[0]

    events = load_all_events(tmp_path / "run")
    environment = next(e for e in events if e["event_class"] == "environment.event")
    observed = next(e for e in events if e["event_class"] == "agent.observed")
    assert environment["event_id"] in observed["caused_by_event_ids"]
    assert observed["payload"]["agent_view"]["observation_ids"]
    record = observed["payload"]["observation_records"][0]
    assert record["source_event_ids"] == [environment["event_id"]]
    assert "oracle" not in json.dumps(environment["payload"]).casefold()


@pytest.mark.asyncio
async def test_scope_without_a_recipient_fails_closed(tmp_path):
    schedule_path = tmp_path / "schedule.json"
    digest = _write_schedule(schedule_path, target="domain/economy")
    driver = DeterministicScheduleDriver(schedule_ref=str(schedule_path), content_hash=digest)
    spine = RunSpine(tmp_path / "run", run_id="environment-no-recipient")
    await spine.start()

    async def behavior(_agent, _rs, _ctx):
        return ActionPlan(result="retire")

    rs = build_runtime(spine, [make_agent("health_agent", behavior, role_id="analyst")])
    rs.environment_scopes = {"health_agent": "domain/health"}
    cause = await spine.emit_event("state.committed", payload={"commitment_id": "spec_t0"})
    with pytest.raises(EnvironmentScheduleError, match="no recipient"):
        await dispatch_after_commit(
            driver, commitment_id="spec_t0", runtime_state=rs, caused_by=cause,
        )
    await spine.finalize("failed")


# --- researcher-side classification block (platform_theory_audit.md §11.3) --- #

def _classified_schedule(path, classification):
    data = {
        "schema_version": 1,
        "waves": [{
            "wave_id": "wave_1",
            "trigger_commitment_id": "spec_t0",
            "packets": [{
                "packet_id": "packet_1", "target_scopes": ["domain/economy"],
                "payload": {"notice_id": "N-7", "notice": "participant-visible fact"},
                "classification": classification,
            }],
        }],
    }
    path.write_text(json.dumps(data, sort_keys=True))
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_classification_validated_and_never_delivered(tmp_path):
    path = tmp_path / "schedule.json"
    digest = _classified_schedule(path, {
        "rule_coverage": "exception", "refs": ["N-7"],
        "expected_scopes": ["domain/economy", "domain/health"],
    })
    driver = DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)
    # host-side visibility for manipulation checks...
    assert driver.classifications["packet_1"]["rule_coverage"] == "exception"
    assert driver.coverage_summary() == {"rule_covered": 0, "exception": 1, "unclassified": 0}
    # ...but the participant packet carries ONLY the payload
    packet = driver.packets_after("spec_t0")[0]
    assert "classification" not in packet.payload
    assert "rule_coverage" not in json.dumps(packet.payload).casefold()


def test_classification_shape_fails_closed(tmp_path):
    path = tmp_path / "schedule.json"
    cases = [
        ({"rule_coverage": "sometimes"}, "rule_coverage"),
        ({"rule_coverage": "rule_covered"}, "names no rule_ref"),
        ({"rule_coverage": "exception", "rule_ref": "R1"}, "names rule_ref"),
        ({"rule_coverage": "exception", "surprise": True}, "unknown keys"),
        ({"rule_coverage": "exception", "refs": ["N-7", "N-7"]}, "unique"),
        ({"rule_coverage": "exception", "shell": {"shell_id": "S1"}}, "classification.shell"),
    ]
    for classification, match in cases:
        digest = _classified_schedule(path, classification)
        with pytest.raises(EnvironmentScheduleError, match=match):
            DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)


def test_classification_refs_unique_across_packets(tmp_path):
    path = tmp_path / "schedule.json"
    data = {
        "schema_version": 1,
        "waves": [{
            "wave_id": "wave_1", "trigger_commitment_id": "spec_t0",
            "packets": [
                {"packet_id": "packet_1", "target_scopes": ["domain/economy"],
                 "payload": {"n": 1},
                 "classification": {"rule_coverage": "exception", "refs": ["N-7"]}},
                {"packet_id": "packet_2", "target_scopes": ["domain/health"],
                 "payload": {"n": 2},
                 "classification": {"rule_coverage": "exception", "refs": ["N-7"]}},
            ],
        }],
    }
    path.write_text(json.dumps(data, sort_keys=True))
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(EnvironmentScheduleError, match="claimed by packets"):
        DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)


# --- later notices on a scheduled case (LK1 context-shift diagnostic, design §3.5) --- #

def _update_schedule(path, update=None, payload=None, base_arrival=7):
    packets = [{"packet_id": "case_a", "target_scopes": ["office/economy"],
                "payload": {"case_id": "C-1", "notice_id": "N-1", "text": "a case"},
                "classification": {"rule_coverage": "exception", "arrival_round": base_arrival,
                                   "response_deadline_round": 10}}]
    if update is not None:
        packets.append({"packet_id": "news_a", "target_scopes": ["office/economy"],
                        "payload": payload or {"notice_id": "N-2", "text": "a later fact"},
                        "classification": update})
    path.write_text(json.dumps({"schema_version": 1, "waves": [
        {"wave_id": "wave_1", "trigger_commitment_id": "spec_t0", "packets": packets}]}, sort_keys=True))
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_an_update_packet_bears_on_a_scheduled_case_and_opens_none(tmp_path):
    path = tmp_path / "schedule.json"
    news = {"rule_coverage": "update", "update_of": "C-1", "arrival_round": 11, "response_deadline_round": 14}
    driver = DeterministicScheduleDriver(schedule_ref=str(path), content_hash=_update_schedule(path, news))
    # the case keeps its own rounds; the news is timed beside it
    assert driver.case_rounds() == {"C-1": {"arrival": 7, "deadline": 10}}
    assert driver.update_rounds() == {"C-1": {"arrival": 11, "deadline": 14, "packet_id": "news_a",
                                              "target_scopes": ["office/economy"]}}
    assert driver.coverage_summary() == {"rule_covered": 0, "exception": 1, "unclassified": 0, "update": 1}
    delivered = driver.packets_at_round(11)
    assert [p.packet_id for p in delivered] == ["news_a"] and delivered[0].update_of == "C-1"
    assert "update_of" not in json.dumps(delivered[0].payload) and "C-1" not in json.dumps(delivered[0].payload)
    # a schedule without one reports none, and its coverage summary is unchanged
    plain = DeterministicScheduleDriver(schedule_ref=str(path), content_hash=_update_schedule(path))
    assert plain.update_rounds() == {} and plain.coverage_summary() == {"rule_covered": 0, "exception": 1, "unclassified": 0}


def test_update_packets_fail_closed_on_shape(tmp_path):
    path = tmp_path / "schedule.json"
    good = {"rule_coverage": "update", "update_of": "C-1", "arrival_round": 11, "response_deadline_round": 14}
    cases = [
        ({"rule_coverage": "update", "arrival_round": 11}, None, "names the case"),                    # no case named
        ({"rule_coverage": "exception", "update_of": "C-1", "arrival_round": 11,
          "response_deadline_round": 14}, None, "names the case"),                                     # only an update names one
        ({**good, "rule_ref": "R1"}, None, "names rule_ref"),
        ({**good, "update_of": "C-9"}, None, "must arrive after the exception case"),                  # not a scheduled case
        ({**good, "arrival_round": 7}, None, "must arrive after the exception case"),                  # not after it
        (good, {"case_id": "C-1", "notice_id": "N-2", "text": "x"}, "must not carry a case_id"),
    ]
    for classification, payload, match in cases:
        digest = _update_schedule(path, classification, payload)
        with pytest.raises(EnvironmentScheduleError, match=match):
            DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)
