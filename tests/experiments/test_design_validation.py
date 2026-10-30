"""Reject invalid study policies before expanding cells or assigning spending caps."""
import pytest

from oaos2.experiments.design import ExperimentDesign, ParityPolicy
from oaos2.experiments.loader import load_design


@pytest.mark.parametrize("regime", ["budget_mached", "", "Both", None])
@pytest.mark.parametrize("basis", ["usd", "tokens"])
def test_unknown_regime_never_expands_extra_cells(regime, basis):
    policy = ParityPolicy(regime=regime, basis=basis, cap_tokens=100)
    with pytest.raises(ValueError, match="unsupported parity regime"):
        ExperimentDesign(parity_policy=policy).validate()
    with pytest.raises(ValueError, match="unsupported parity regime"):
        policy.resolve_budgets(base_cap_usd=1)
    with pytest.raises(ValueError, match="unsupported parity regime"):
        policy.resolve_regimes(base_cap_usd=1)


@pytest.mark.parametrize("regime,expected", [("budget_matched", [("budget_matched", 1)]),
                                            ("unconstrained", [("unconstrained", 3)]),
                                            ("both", [("budget_matched", 1), ("unconstrained", 3)])])
def test_supported_regimes_keep_their_declared_cells_and_caps(regime, expected):
    for basis in ("usd", "tokens"):
        policy = ParityPolicy(regime=regime, basis=basis, cap_tokens=100)
        budgets = policy.resolve_budgets(base_cap_usd=1)
        assert [(name, b["cap_usd"]) for name, b in budgets] == expected
        if basis == "tokens":
            assert [b["cap_output_tokens"] for _, b in budgets] == [cap * 100 for _, cap in expected]


def test_loader_rejects_mode_typo_at_config_read(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    exp = lib / "experiments"
    exp.mkdir(parents=True)
    (exp / "typo.yaml").write_text("name: typo\nmode: confrimatory\n")
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    with pytest.raises(ValueError, match="confrimatory"):
        load_design("typo")
    (exp / "typo.yaml").write_text("name: typo\nmode: calibration\nparity_policy: {regime: budget_mached}\n")
    with pytest.raises(ValueError, match="unsupported parity regime"):
        load_design("typo")
