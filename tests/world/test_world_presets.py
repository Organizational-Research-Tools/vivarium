"""The competition study's arms, written as the materials workshop plus what each arm sets, are the
presets the study ran (library/organizations/competition_*.yaml against the frozen
pc1_supplier_g_xmodel7*.yaml)."""
from __future__ import annotations

import dataclasses

import pytest

from oaos2.organizations.compare import preset_differences
from oaos2.organizations.loader import load_org_spec, read_preset

ARMS = {"competition_competitive": "pc1_supplier_g_xmodel7",
        "competition_cooperative": "pc1_supplier_g_xmodel7_cooperative"}
VARIED = ["live_coordination.allocation", "live_coordination.deliberation_text", "live_coordination.institution",
          "live_coordination.objective_text", "live_coordination.success_cap", "live_coordination.success_floor",
          "live_coordination.urgency_text"]


def _settings(spec) -> dict:
    return {k: v for k, v in dataclasses.asdict(spec).items() if k not in ("preset_id", "source_ref", "base_refs")}


@pytest.mark.parametrize("overlay,frozen", ARMS.items())
def test_each_arm_resolves_to_the_preset_the_study_ran(overlay, frozen):
    assert preset_differences(overlay, frozen) == []
    (written, bases), (ran, _) = read_preset(overlay), read_preset(frozen)
    assert {k: v for k, v in written.items() if k != "preset_id"} == {k: v for k, v in ran.items() if k != "preset_id"}
    spec = load_org_spec(overlay)
    assert [b.name for b in spec.base_refs] == ["materials_workshop.yaml"]
    assert _settings(spec) == _settings(load_org_spec(frozen))


def test_the_arms_differ_only_in_the_credit_institution_and_its_texts():
    varied = [d["setting"] for d in preset_differences(*ARMS)]
    assert varied == VARIED == [d["setting"] for d in preset_differences(*ARMS.values())]


def test_the_workshop_is_a_base_and_is_not_run_alone():
    base, _ = read_preset("materials_workshop")
    assert base["base_only"] is True and "institution" not in base["live_coordination"]
    with pytest.raises(ValueError, match="base for other presets"):
        load_org_spec("materials_workshop")


def test_every_released_preset_loads_or_is_a_base():
    from oaos2.organizations.loader import available_org_specs

    names = available_org_specs()
    assert {"materials_workshop", *ARMS, *ARMS.values(), "example_rule_injury"} <= set(names)
    for name in names:
        if not read_preset(name)[0].get("base_only"):
            load_org_spec(name)


def test_the_example_study_changes_one_setting_of_the_competitive_arm():
    assert preset_differences("competition_competitive", "example_rule_injury") == [
        {"setting": "live_coordination.rule_level", "a": "approved_list", "b": "injury"}]
