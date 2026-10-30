"""Executable-code pins must survive committing their own evidence file."""
import os
from types import SimpleNamespace

import pytest

from oaos2.experiments.source_identity import source_code_sha256


def _write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.mark.parametrize("name", ["oaos2/runtime.py", "scripts/check.py",
                                  "library/tasks/custom/plugin.py", "pyproject.toml", "uv.lock"])
def test_executable_source_and_dependency_changes_alter_identity(tmp_path, name):
    path = _write(tmp_path, name, "before\n")
    baseline = source_code_sha256(tmp_path)
    os.utime(path, (100, 100))
    assert source_code_sha256(tmp_path) == baseline
    path.write_text("after\n")
    assert source_code_sha256(tmp_path) != baseline
    path.write_text("before\n")
    assert source_code_sha256(tmp_path) == baseline
    path.rename(path.with_name("renamed" + path.suffix))
    assert source_code_sha256(tmp_path) != baseline


def test_committing_document_and_pin_content_cannot_change_code_identity(tmp_path):
    _write(tmp_path, "oaos2/runtime.py", "print('fixed code')\n")
    baseline = source_code_sha256(tmp_path)
    for name in ("docs/study.md", "library/tasks/custom/INSTRUMENT_DESIGN.md",
                 "library/experiments/evidence/launch_pins.json", ".git/HEAD"):
        _write(tmp_path, name, baseline)
        assert source_code_sha256(tmp_path) == baseline
    _write(tmp_path, "oaos2/new_module.py", "NEW = True\n")
    assert source_code_sha256(tmp_path) != baseline
    (tmp_path / "oaos2/new_module.py").unlink()
    assert source_code_sha256(tmp_path) == baseline


def test_same_tree_has_same_identity_in_another_checkout(tmp_path):
    for folder in ("one", "two"):
        _write(tmp_path / folder, "oaos2/a.py", "a = 1\n")
        _write(tmp_path / folder, "scripts/b.py", "b = 2\n")
    assert source_code_sha256(tmp_path / "one") == source_code_sha256(tmp_path / "two")


def test_source_state_records_code_hash_and_explicit_failure(monkeypatch):
    from oaos2.experiments import runner
    monkeypatch.setattr('oaos2.experiments.source_identity.source_code_sha256', lambda root: 'sha256:code')
    monkeypatch.setattr(runner.subprocess, 'run', lambda args, **kw: SimpleNamespace(
        stdout='commit\n' if 'rev-parse' in args else b''))
    runner._source_state.cache_clear()
    try:
        assert runner._source_state()['source_code_sha256'] == 'sha256:code'
        def fail(root):
            raise OSError('unreadable source')
        monkeypatch.setattr('oaos2.experiments.source_identity.source_code_sha256', fail)
        runner._source_state.cache_clear()
        assert runner._source_state()['source_code_sha256'] is None
    finally:
        runner._source_state.cache_clear()


def test_research_setup_changes_with_code_but_not_commit_metadata(monkeypatch):
    from oaos2.experiments.runner import _research_setup_sha
    from oaos2.organizations.loader import load_org_spec
    from oaos2.tasks.loader import load_task_pack
    state = dict(source_code_sha256='sha256:code-a', source_commit='first-commit')
    monkeypatch.setattr('oaos2.experiments.runner._source_state', lambda: dict(state))
    pack = load_task_pack('budget_execution', profile='budget_vertical_v14_clocked')
    org = load_org_spec('budget_execution_summary_clocked')
    kwargs = dict(tier='unprogrammable', model_ref='anthropic/claude-sonnet-4-6',
                  context_budget=None, cap_usd=8.0, cap_output_tokens=None,
                  final_reserve_tokens=0, parity_basis='usd')
    baseline = _research_setup_sha(pack, org, **kwargs)
    state['source_commit'] = 'commit-containing-launch-pins'
    assert _research_setup_sha(pack, org, **kwargs) == baseline
    state['source_code_sha256'] = 'sha256:code-b'
    assert _research_setup_sha(pack, org, **kwargs) != baseline


def test_git_unavailability_does_not_discard_readable_code_identity(monkeypatch):
    from oaos2.experiments import runner
    monkeypatch.setattr('oaos2.experiments.source_identity.source_code_sha256', lambda root: 'sha256:code')
    def fail(*args, **kwargs):
        raise OSError('no Git metadata')
    monkeypatch.setattr(runner.subprocess, 'run', fail)
    runner._source_state.cache_clear()
    try:
        assert runner._source_state()['source_code_sha256'] == 'sha256:code'
        assert runner._source_state()['source_commit'] is None
    finally:
        runner._source_state.cache_clear()


async def test_confirmatory_sweep_refuses_unreadable_source_before_dispatch(monkeypatch, tmp_path):
    from oaos2.experiments import runner
    from oaos2.experiments.design import ExperimentDesign, ParityPolicy
    from oaos2.experiments.confirmatory import ConfirmatoryReadinessError
    monkeypatch.setattr(runner, '_source_state', lambda: {'source_code_sha256': None})
    async def forbidden(*args, **kwargs):
        pytest.fail('unidentified code reached a live dispatch')
    monkeypatch.setattr(runner, 'run_org_live', forbidden)
    prereg = tmp_path / 'prereg.md'
    prereg.write_text('STATUS: FINAL\n')
    design = ExperimentDesign(mode='confirmatory', preregistration_ref=str(prereg),
                              factors={'org_preset': ['single_agent'], 'difficulty': ['hard'],
                                       'model': ['stub/deterministic']},
                              parity_policy=ParityPolicy(regime='budget_matched', cap_usd=1))
    with pytest.raises(ConfirmatoryReadinessError, match='executable-source identity'):
        await runner.run_sweep(design, tmp_path / 'runs', execution='live')
    assert not (tmp_path / 'runs').exists()
