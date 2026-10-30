import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from oaos2.experiments.confirmatory import ConfirmatoryReadinessError, assert_confirmatory_ready
from oaos2.experiments.runner import _research_setup_sha
from oaos2.organizations.loader import load_org_spec
from oaos2.tasks.loader import load_task_pack


def test_setup_fingerprint_tracks_effective_limits_and_materials(monkeypatch, tmp_path):
    monkeypatch.setattr('oaos2.experiments.runner._source_state', lambda: {})
    pack = load_task_pack('budget_execution', profile='budget_vertical_v14_clocked')
    org = load_org_spec('budget_execution_summary_clocked')
    kwargs = dict(tier='unprogrammable', model_ref='anthropic/claude-sonnet-4-6',
                  context_budget=None, cap_usd=8.0, cap_output_tokens=None,
                  final_reserve_tokens=0, parity_basis='usd')
    base = _research_setup_sha(pack, org, **kwargs)
    assert base == _research_setup_sha(pack, org, **kwargs)
    changed = deepcopy(org)
    changed.roles[0].max_calls_per_slot = 32
    assert base != _research_setup_sha(pack, changed, **kwargs)
    assert base != _research_setup_sha(pack, org, **{**kwargs, 'cap_usd': 9.0})
    assert base != _research_setup_sha(pack, org, **{**kwargs, 'context_budget': 10000})
    changed_pack = deepcopy(pack)
    changed_pack.clock = pack.clock.override({'calls_per_day': 32})
    assert base != _research_setup_sha(changed_pack, org, **kwargs)
    changed_pack = deepcopy(pack)
    changed_pack.data_dir = tmp_path
    (tmp_path / 'data.csv').write_text('x\n1\n')
    a = _research_setup_sha(changed_pack, org, **kwargs)
    (tmp_path / 'data.csv').write_text('x\n2\n')
    assert a != _research_setup_sha(changed_pack, org, **kwargs)


def test_readiness_requires_exact_backed_setup(tmp_path):
    setup = 'sha256:' + 'a' * 64
    batch = tmp_path / 'batch'
    (batch / 'trace').mkdir(parents=True)
    (batch / 'run_status.json').write_text(json.dumps(dict(
        model_ref='model', difficulty='tier', cost_usd=1, closed=True, archive_valid=True)))
    manifest = dict(task_pack_id='pack', mode='calibration', extensions={'research_setup_sha256': setup})
    (batch / 'manifest.json').write_text(json.dumps(manifest))
    (batch / 'trace' / 'events.jsonl').write_text('{"event_class":"run.completed"}\n')
    prereg = tmp_path / 'prereg.md'
    prereg.write_text('STATUS: FINAL\n')
    evidence = dict(kind='capacity_calibration', task_pack='pack', tier='tier', model_ref='model',
                    capacity_established=True, batch_ref=str(batch), setup_sha256s=[setup])
    ep = tmp_path / 'evidence.json'
    def check(required, doc=evidence):
        ep.write_text(json.dumps(doc))
        return assert_confirmatory_ready(
            org_specs=[SimpleNamespace(preset_id='org', live_coordination={})],
            preregistration_ref=prereg, evidence={'capacity_calibration': {
                'path': str(ep), 'sha256': hashlib.sha256(ep.read_bytes()).hexdigest()}},
            task_pack='pack', model_refs=('model',), tiers=('tier',), setup_sha256s=required)
    check((setup,))
    with pytest.raises(ConfirmatoryReadinessError, match='resolved setup'):
        check(())
    with pytest.raises(ConfirmatoryReadinessError, match='does not cover'):
        check(('sha256:' + 'b' * 64,))
    legacy = {k: v for k, v in evidence.items() if k != 'setup_sha256s'}
    with pytest.raises(ConfirmatoryReadinessError, match='legacy evidence'):
        check((setup,), legacy)
    manifest['extensions']['research_setup_sha256'] = 'sha256:' + 'b' * 64
    (batch / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ConfirmatoryReadinessError, match='lack backing'):
        check((setup,))


@pytest.mark.parametrize('cap', [float('nan'), float('inf'), -1, 0, True])
async def test_live_cap_refused_before_creating_run_resources(tmp_path, cap):
    from oaos2.experiments.runner import run_org_live
    org = load_org_spec('single_agent')
    root = tmp_path / 'runs'
    with pytest.raises(ValueError):
        await run_org_live(org, root, tier='hard', cap_usd=cap)
    assert not root.exists()


@pytest.mark.parametrize('cap', [float('nan'), float('inf'), -1, 0, True])
@pytest.mark.parametrize('regime', ['budget_matched', 'unconstrained'])
async def test_sweep_cap_refused_before_first_dispatch(tmp_path, cap, regime, monkeypatch):
    from oaos2.experiments.design import ExperimentDesign, ParityPolicy
    from oaos2.experiments.runner import run_sweep
    async def forbidden(*args, **kwargs):
        pytest.fail('invalid cap reached live dispatch')
    monkeypatch.setattr('oaos2.experiments.runner.run_org_live', forbidden)
    design = ExperimentDesign(factors={'org_preset': ['single_agent'],
                                      'difficulty': ['hard'], 'model': ['stub/deterministic']},
                              parity_policy=ParityPolicy(regime=regime))
    with pytest.raises(ValueError):
        await run_sweep(design, tmp_path / 'runs', execution='live', cap_usd=cap)
    assert not (tmp_path / 'runs').exists()
