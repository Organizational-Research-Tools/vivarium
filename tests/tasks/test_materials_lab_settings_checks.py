"""Settings the materials lab would read and then ignore are refused when the preset loads (release
review, October 29, 2026): the credit institution's settings without an institution, and a board setting
the board does not read."""
from __future__ import annotations

import dataclasses

import pytest

from oaos2.communication.board import Board
from oaos2.organizations.loader import load_org_spec
from oaos2.tasks.plugins.materials_lab.settings import INSTITUTION_ONLY


def _with(preset: str, **changes):
    spec = load_org_spec(preset)
    return dataclasses.replace(spec, live_coordination={**spec.live_coordination, **changes})


@pytest.mark.parametrize("name,value", [("contest", True), ("program_lines", True), ("success_floor", 4),
                                        ("success_cap", 3), ("credit_threshold", 2), ("program_target", 2),
                                        ("challenges", True), ("state_feasible_count", False)])
def test_an_institution_setting_without_an_institution_is_refused(name, value):
    assert name in INSTITUTION_ONLY
    spec = _with("materials_trio", **{name: value})
    assert not spec.live_coordination.get("institution")
    with pytest.raises(ValueError, match="belong to an institution"):
        spec.validate()


@pytest.mark.parametrize("name", ["success_floor", "success_cap"])
def test_the_success_floor_and_cap_need_divisible_credit(name):
    spec = _with("pc1_supplier_g_xmodel7_cooperative", **{name: 3})
    assert spec.live_coordination["institution"] == "cooperative"
    with pytest.raises(ValueError, match="need allocation: divisible"):
        spec.validate()


def test_the_same_settings_load_under_an_institution():
    spec = load_org_spec("pc1_supplier_g_xmodel7")
    assert spec.live_coordination["institution"] == "competitive"
    assert {"contest", "program_lines", "success_floor", "success_cap"} <= set(spec.live_coordination)


def test_a_misspelled_board_setting_is_refused_when_the_preset_loads_and_by_the_board():
    with pytest.raises(ValueError, match=r"unknown board setting\(s\) \['post_limit'\]"):
        _with("materials_trio", board={"form": "forum", "post_limit": 400}).validate()
    with pytest.raises(ValueError, match=r"unknown board setting\(s\) \['post_limit'\]"):
        Board().configure({"form": "forum", "post_limit": 400})
    Board().configure({"form": "forum", "post_cap": 400, "index_page": 10, "thread_page": 4})



def test_every_setting_has_a_type_and_a_wrong_type_is_refused_by_name():
    from oaos2.tasks.plugins.materials_lab.settings import SETTINGS, TYPES
    typed = set().union(*TYPES.values())
    assert typed == set(SETTINGS) and sum(len(v) for v in TYPES.values()) == len(typed)
    for name, value, kind in [("concern_effect_stated", "false", "yes or no"), ("success_floor", "four", "a whole number"),
                              ("reminder_minutes", 10, "a list"), ("density", "0.3", "a number"),
                              ("success_cap", True, "a whole number")]:
        spec = _with("pc1_supplier_g_xmodel7", **{name: value})
        with pytest.raises(ValueError, match=f"{name} must be {kind}"):
            spec.validate()


def test_a_null_leaves_a_setting_unset_and_whole_numbers_are_numbers():
    _with("pc1_supplier_g_xmodel7", density=1, guidance_text=None).validate()
