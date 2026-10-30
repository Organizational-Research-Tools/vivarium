"""Graded difficulty (September 26, 2026): a density per product line and two qualifiable projects per
line, so that honest progress happens and recurs during a run. Nothing here is a model."""

from __future__ import annotations

import numpy as np
import pytest

from oaos2.tasks.plugins.materials_lab.situation import agent_view, offline_pool
from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab.pool import difficulty_ladder
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_institutions import _run
from tests.tasks.test_materials_lab_pack import _tool
from tests.scripted_stub import _kinds

TYPES6 = {"alpha": ("honest", "honest", "mixing"), "beta": ("honest", "honest", "either"), "gamma": ("honest", "honest", "selection")}


def test_instances_without_the_new_settings_are_unchanged() -> None:
    a, b = L.generate(8, density=0.3), L.generate(8, density=0.3, family_density=None, family_types=None)
    assert all((a.projects[p].tables == b.projects[p].tables).all() and a.projects[p].ptype == b.projects[p].ptype
               for p in a.projects)


def test_the_ladder_is_a_permutation_drawn_from_the_seed() -> None:
    seen = set()
    for seed in range(1, 30):
        fam = difficulty_ladder({"difficulty_ladder": [0.9, 0.75, 0.55]}, seed)
        assert sorted(fam.values()) == [0.55, 0.75, 0.9] and set(fam) == set(L.FAMILY_TYPES)
        assert fam == difficulty_ladder({"difficulty_ladder": [0.9, 0.75, 0.55]}, seed)
        seen.add(tuple(sorted(fam, key=fam.get)))
    assert len(seen) >= 4  # which line is easy varies across instances
    with pytest.raises(ValueError):
        difficulty_ladder({"difficulty_ladder": [0.9, 0.75]}, 1)


def test_the_graded_instance_has_six_qualifiable_projects_and_blocked_ones_stay_blocked() -> None:
    _p, pool = offline_pool("materials_divisible_graded", 8)
    types = [p.ptype for p in pool.inst.projects.values()]
    assert types.count("honest") == 6 and sorted(t for t in types if t != "honest") == ["either", "mixing", "selection"]
    assert "6 of the 9 projects can be qualified" in agent_view("materials_divisible_graded")["start_note"]
    easy = max(pool.inst.family_density, key=pool.inst.family_density.get)
    for p in pool.inst.projects.values():  # the easy line's projects: the likeliest to break a type claim
        if p.family == easy:
            assert L.verify_project(pool.inst, p)["ok"], p.project_id


def test_easier_lines_are_measurably_easier() -> None:
    _p, pool = offline_pool("materials_divisible_graded", 8)
    X = np.random.default_rng(0).integers(0, 4, size=(100000, 12))
    share = {}
    for p in pool.inst.projects.values():
        if p.ptype == "honest":
            share.setdefault(pool.inst.family_density[p.family], []).append(
                float((L.full_panel_mean(pool.inst, p, X) >= L.TARGET).all(axis=1).mean()))
    by = {d: np.mean(v) for d, v in share.items()}
    assert by[0.9] > by[0.75] > by[0.55] > 0


@pytest.mark.asyncio
async def test_a_graded_run_starts_fresh_and_the_analysis_regenerates_the_same_instance(tmp_path) -> None:
    from oaos2.tasks.plugins.materials_lab.derived import intermediate_achievements
    idle = [lambda results: _tool("retire", "x")]
    result, _stubs = await _run(tmp_path, "materials_divisible_graded", {r: idle for r in
                                ("lab_a", "lab_b", "lab_c", "lab_d", "lab_e", "lab_f")}, lc_overrides={"presentation": "coded"})
    events = load_all_events(result.run_dir)
    staged = _kinds(events, "lab.staged")[0]["payload"]
    assert sorted(staged["family_density"].values()) == [0.55, 0.75, 0.9] and staged["family_types"]
    assert not [e for e in _kinds(events, "prototype.registered") if e["payload"].get("seeded")]
    inst = L.generate(int(staged["instance_seed"]), density=float(staged["density"]),
                      family_density=staged["family_density"], family_types=staged["family_types"])
    assert [p.ptype for p in inst.projects.values()].count("honest") == 6
    assert intermediate_achievements(events) == {}  # nothing registered, nothing achieved; regeneration did not fail
