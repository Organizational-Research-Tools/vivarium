"""Per-role model binding gates (Study C1h): the realized-vs-declared certificate
over ``model.invoked`` and the cross-cell map check inside ``confound_check``.
The scalar run-level ``model_ref`` gate is untouched; the map is compared WITHIN a
preset (it is the preset's treatment) and may differ ACROSS presets."""

from __future__ import annotations

import pytest

from oaos2.experiments.runner import CellResult
from oaos2.organizations.confound_check import (
    ConfoundViolation,
    certify_role_model_refs,
    confound_check,
    realized_role_model_refs,
)

S, X = "anthropic/claude-sonnet-4-6", "openai/gpt-5"


def _ev(agent, ref, cls="model.invoked"):
    return {"event_class": cls, "agent_id": agent, "payload": {"model_ref": ref}}


def test_certificate_passes_on_exact_realization() -> None:
    events = [_ev("office_a", S), _ev("office_b", X), _ev("office_a", S),
              _ev("office_a", "ignored", cls="model.responded"),  # only invocations count
              {"event_class": "run.started", "payload": {}}]  # no agent → ignored
    realized = certify_role_model_refs(events, {"office_a": S, "office_b": X})
    assert realized == {"office_a": [S], "office_b": [X]}
    # A declared role that never invoked a model is absent, not a violation.
    assert certify_role_model_refs([_ev("office_a", S)], {"office_a": S, "office_b": X}) == {
        "office_a": [S]}
    assert realized_role_model_refs([]) == {}


@pytest.mark.parametrize("events, declared", [
    ([_ev("office_a", X)], {"office_a": S, "office_b": X}),          # wrong ref
    ([_ev("office_a", S), _ev("office_a", X)], {"office_a": S}),     # two refs on one role
    ([_ev("ghost", S)], {"office_a": S}),                            # undeclared agent invoked
])
def test_certificate_refuses_any_mismatch(events, declared) -> None:
    with pytest.raises(ConfoundViolation, match="apparatus fault"):
        certify_role_model_refs(events, declared)


def _cell(preset: str, role_refs=None, **kw) -> CellResult:
    base = dict(model_ref=S, closed=True, passed=False, label="unassisted", archive_valid=True,
                pricing_table_version="v", pricing_table_hash="sha256:aaa",
                cache_policy_fingerprint="fp", runtime="raw_api")
    base.update(kw)
    return CellResult(preset_id=preset, role_model_refs=role_refs or {}, **base)


def test_maps_may_differ_across_presets_but_not_within_one() -> None:
    ss, sx, xs = {"office_a": S, "office_b": S}, {"office_a": S, "office_b": X}, {"office_a": X, "office_b": S}
    # Different presets carrying different maps is the C1h design itself.
    confound_check([_cell("dyad", ss), _cell("dyad_hSX", sx), _cell("dyad_hXS", xs)],
                   mode="confirmatory")
    # Replications of ONE preset that ran on different per-role models are two conditions.
    with pytest.raises(ConfoundViolation, match="differs across cells of one preset"):
        confound_check([_cell("dyad_hSX", sx), _cell("dyad_hSX", xs)], mode="confirmatory")
    # Legacy cells without the field stay comparable; the scalar gate still bites.
    confound_check([_cell("a"), _cell("b")], mode="pilot")
    with pytest.raises(ConfoundViolation, match="model snapshot differs"):
        confound_check([_cell("a"), _cell("b", model_ref=X)], mode="pilot")
