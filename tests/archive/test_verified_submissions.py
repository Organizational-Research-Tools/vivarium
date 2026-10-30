import hashlib
import json

import pytest

from oaos2.archive.submissions import SubmissionIntegrityError, read_verified_submissions


def _archive(root):
    sub = root / 'captured' / 'submitted'
    sub.mkdir(parents=True)
    data = json.dumps({'selected_option': 'A1'}).encode()
    (sub / 'choice.json').write_bytes(data)
    event = {'sequence_number': 0, 'event_class': 'state.committed', 'payload': {
        'state_commitment': {'commitment_id': 'choice', 'payload_ref': 'submitted/choice.json',
                             'content_hash': 'sha256:' + hashlib.sha256(data).hexdigest()}}}
    (root / 'trace').mkdir()
    (root / 'trace' / 'events.jsonl').write_text(json.dumps(event) + '\n')
    return sub, event


def test_verified_reader_accepts_original_bytes(tmp_path):
    _archive(tmp_path)
    assert read_verified_submissions(tmp_path) == {'choice': {'selected_option': 'A1'}}


async def test_live_coordinator_payload_before_capture_and_capture_priority(tmp_path):
    from oaos2.kernel.run_dir import RunDir
    from oaos2.outcomes.commit import OutcomeCoordinator
    from oaos2.outcomes.contracts import Commitment, OutcomeContract
    from oaos2.trace.spine import RunSpine

    rd = RunDir.create(tmp_path, 'experiment', 'pack', 'run')
    spine = RunSpine(rd.root, run_id='run')
    await spine.start()
    try:
        contract = OutcomeContract(outcome_id='answer', commitments=[
            Commitment(commitment_id='final', kind='artifact_submission')])
        coordinator = OutcomeCoordinator(contract, spine, rd.submitted)
        await coordinator.commit(commitment_id='final', payload={'answer': 42},
                                 agent_id='author', session_id='session')
        await spine.queue.queue.join()
        assert read_verified_submissions(rd.root) == {'final': {'answer': 42}}
        captured = rd.captured / 'submitted'
        captured.mkdir()
        # A partially captured directory must not hide missing evidence by reading
        # the intact active copy instead.
        with pytest.raises(SubmissionIntegrityError, match='missing'):
            read_verified_submissions(rd.root)
        (captured / 'final.json').write_bytes((rd.submitted / 'final.json').read_bytes())
        (rd.submitted / 'final.json').write_text('{}')
        assert read_verified_submissions(rd.root) == {'final': {'answer': 42}}
    finally:
        await spine.finalize('completed')


def test_legacy_submission_directory_remains_readable(tmp_path):
    sub, _ = _archive(tmp_path)
    sub.rename(tmp_path / 'submitted')
    assert read_verified_submissions(tmp_path) == {'choice': {'selected_option': 'A1'}}


@pytest.mark.parametrize('change', ['edit', 'missing', 'extra', 'duplicate', 'wrong_ref', 'missing_hash'])
def test_verified_reader_rejects_corrupted_evidence(tmp_path, change):
    sub, event = _archive(tmp_path)
    if change == 'edit':
        (sub / 'choice.json').write_text('{"selected_option":"A2"}')
    elif change == 'missing':
        (sub / 'choice.json').unlink()
    elif change == 'extra':
        (sub / 'uncommitted.json').write_text('{}')
    elif change == 'wrong_ref':
        event['payload']['state_commitment']['payload_ref'] = '../choice.json'
    elif change == 'missing_hash':
        event['payload']['state_commitment'].pop('content_hash')
    events = [event, event] if change == 'duplicate' else [event]
    with pytest.raises(SubmissionIntegrityError):
        read_verified_submissions(tmp_path, events=events)
