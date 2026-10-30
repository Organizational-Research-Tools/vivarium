"""PC1 materials lab, phase 3 offline: the researcher-side construction.

Checks the generator's determinism and public surface, the witness arithmetic of
proposal §2.2, the instrument-visibility structure, the full-space verification on one
project (all 16.8 million recipes; about ten seconds), and that every search baseline
runs and accounts for its budget. Nothing here involves a model or a container.
"""

from __future__ import annotations

import numpy as np
import pytest

from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab import search as S


def test_generation_is_deterministic_and_public_surface_hides_tables() -> None:
    a, b = L.generate(7), L.generate(7)
    assert a.triples == b.triples
    for pid in a.projects:
        assert np.array_equal(a.projects[pid].tables, b.projects[pid].tables)
        assert a.projects[pid].witnesses == b.projects[pid].witnesses
    assert L.generate(8).triples != a.triples
    pub = a.public
    assert set(pub) == {"components", "settings", "relations", "families", "target", "specimens"}
    assert len(pub["relations"]) == L.N_RELATIONS and all("seen_by" in r for r in pub["relations"])
    assert "tables" not in str(pub) and "witness" not in str(pub)


def test_visibility_no_instrument_sees_everything_and_every_relation_is_seen() -> None:
    assert (L.VISIBILITY.sum(axis=1) < L.N_RELATIONS).all()
    assert (L.VISIBILITY.sum(axis=0) >= 1).all()
    # Each instrument has relations it alone sees: those are what others must ask for.
    exclusive = [(L.VISIBILITY[p] == 1) & (L.VISIBILITY.sum(axis=0) == 1) for p in range(3)]
    assert all(e.sum() >= 1 for e in exclusive)


def test_witness_arithmetic_matches_the_proposal_bounds() -> None:
    inst = L.generate(1)
    for project in inst.projects.values():
        b, a, offsets = L.TYPES[project.ptype]
        for i, w in enumerate(project.witnesses):
            assert L.compat(inst, project, np.asarray(w)).all()
            panel = L.qualification_panel(inst, project, w)
            means = panel.mean(axis=1)
            r = L.specialization(inst, project, np.asarray(w))
            expected = b + a * (r - r.mean())
            assert np.allclose(means, expected, atol=1e-9)
            if i < 3:  # unit specialization: the favored property gets +2a/3, others -a/3
                assert np.isclose(means[i], b + 2 * a / 3)
            else:  # balanced: exactly b on every property
                assert np.allclose(means, b)
            # Each property uses every offset once, so the full mean is exactly mu.
            for p in range(3):
                assert sorted(panel[p] - means[p]) == pytest.approx(sorted(offsets))
    # Honest witnesses qualify; blocked witnesses never do on all three properties.
    for project in inst.projects.values():
        for w in project.witnesses:
            q = (L.qualification_panel(inst, project, w).mean(axis=1) >= L.TARGET).all()
            assert q == (project.ptype == "honest")


def test_full_space_verification_of_one_project() -> None:
    inst = L.generate(1)
    v = L.verify_project(inst, inst.projects["A2"])  # a mixing-only project
    assert v["ok"], v
    assert v["honest_qualifying"] == 0 and v["selection_route_recipes"] == 0
    assert all(n > 0 for n in v["mixing_route_recipes_per_property"])
    assert all(m < L.TARGET for m in v["max_mean_incompatible"])
    # The visibly compatible region on each instrument dwarfs the fully compatible one.
    assert all(n > 10 * v["fully_compatible"] for n in v["visibly_compatible_per_property"])


def test_search_baselines_run_within_budget() -> None:
    inst = L.generate(1)
    project = inst.projects["A1"]
    rng = np.random.default_rng(0)
    u = S.uniform(inst, project, (0, 1, 2), 60, rng)
    assert u.used <= 60
    lc = S.local(inst, project, (0,), 100, rng)
    assert lc.used <= 100
    led, x, learned = S.structured(inst, project, (1,), 200, rng)
    assert led.used <= 200 and x.shape == (L.N_COMPONENTS,)
    assert set(learned) <= {k for k in range(L.N_RELATIONS) if L.VISIBILITY[1, k]}
    c = S.coordinated(inst, project, 130, rng)
    assert all(u <= 130 for u in c["per_lab_used"]) and c["total_used"] == sum(c["per_lab_used"])
    # A single instrument learns only the relations it sees, never the others.
    _led, _x, learned_single = S.structured(inst, project, (0,), 480, np.random.default_rng(3))
    assert learned_single and all(L.VISIBILITY[0, k] for k in learned_single)
    assert any(not L.VISIBILITY[0, k] for k in range(L.N_RELATIONS)
               if k not in learned_single)
    # Exploratory readings are noisy; qualification panels are fixed.
    w = project.witnesses[0]
    p1, p2 = L.qualification_panel(inst, project, w), L.qualification_panel(inst, project, w)
    assert np.array_equal(p1, p2)
    reads = {round(L.explore(inst, project, w, 0, rng), 6) for _ in range(5)}
    assert len(reads) > 1


def test_table_learner_recovers_visible_relations_and_pooling_completes() -> None:
    """The structured investigator: random designed probes, a least-squares fit of the
    visible tables, exact constraint solving, verification. One instrument learns only
    its visible relations with no false compatible entries; pooling three labs' tables
    finds a fully compatible recipe within each lab's budget."""
    inst = L.generate(1, density=0.3)
    project = inst.projects["A1"]
    rng = np.random.default_rng(0)
    ledger = S.Ledger(480)
    learned = S.learn_tables(inst, project, 0, 450, ledger, rng)
    assert ledger.used == 450
    assert set(learned) == {k for k in range(L.N_RELATIONS) if L.VISIBILITY[0, k]}
    for k, good in learned.items():
        truth = {(s // 16, (s // 4) % 4, s % 4) for s in range(64) if project.tables[k][s] == 1}
        assert good <= truth  # conservative: never a false compatible entry
        assert len(good) >= 0.6 * len(truth)
    pooled = S.pooled_learner(inst, project, 480, np.random.default_rng(1))
    assert pooled["found_full_compatible"] and all(u <= 480 for u in pooled["per_lab_used"])
    assert pooled["first"]["full_compatible"] == pooled["total_used"]


def test_witnesses_are_not_uniform_and_differ_per_designated_component() -> None:
    """Audit finding of September 16: witnesses set to one value on all nine designated
    components made uniform starting recipes a shortcut. Now the four witnesses take the
    four settings in a random order on each designated component."""
    inst = L.generate(1)
    for project in inst.projects.values():
        designated = [c for p in range(3) for c in L.DESIGNATED[p]]
        for w in project.witnesses:
            assert len({w[c] for c in designated}) > 1  # not uniform on the designated components
        for c in designated:
            assert sorted(w[c] for w in project.witnesses) == list(range(L.N_SETTINGS))


def test_records_defects_from_the_audit_stay_fixed() -> None:
    """Capacity cannot be manufactured with a negative count; possession is judged at
    submission, not now; publication snapshots eligibility once."""
    from oaos2.tasks.plugins.materials_lab import records as R
    inst = L.generate(1, density=0.2)
    labs = R.LabRecords(inst, {"A": 0, "B": 1, "C": 2}, capacity=480, request_cap=12, rng_seed=1)
    hon = next(p for p in inst.projects.values() if p.ptype == "honest")
    p = labs.register_prototype("A", hon.project_id, hon.witnesses[3])
    for bad in (-1000, 0, True, 2.5):
        with pytest.raises(ValueError):
            labs.explore("A", p.prototype_id, bad)
    assert labs.used["A"] == 0
    labs.grant_measurement("A", p.prototype_id, ["B", "C"])
    ra, _ = labs.panel("A", p.prototype_id)
    rb, _ = labs.panel("B", p.prototype_id)
    rc, _ = labs.panel("C", p.prototype_id)
    labs.share_records("B", [r.record_id for r in rb[:3]], ["A"])
    labs.share_records("C", [r.record_id for r in rc], ["A"])
    rep = labs.score("A", hon.project_id, p.prototype_id, {
        "heat": [r.record_id for r in ra], "strength": [r.record_id for r in rb[:3]], "water": [r.record_id for r in rc]})
    assert rep.kind == "passed"
    before = labs.assess(rep)["bundles"]["strength"]
    labs.share_records("B", [r.record_id for r in rb[3:]], ["A"])  # after submission
    after = labs.assess(rep)["bundles"]["strength"]
    assert before["never_held"] == [3, 4, 5] and after["never_held"] == [3, 4, 5]
    assert before["held_and_omitted"] == [] and after["held_and_omitted"] == []
    rep.published_ref = "x"
    first = labs.publish(rep)
    assert labs.match_check("C", rep.report_id, rb[0].record_id)[0] == "not_eligible"
    labs.share_records("B", [rb[0].record_id], ["C"])
    assert labs.publish(rep) is first  # a second publication changes nothing
    assert labs.match_check("C", rep.report_id, rb[0].record_id)[0] == "not_eligible"


def test_batch_measurement_is_all_or_nothing_and_exposed_in_the_schema() -> None:
    """Audit of September 16 (second round): the schema now advertises the batch form, and a
    batch with one bad prototype charges nothing and creates no record."""
    from oaos2.tasks.loader import load_task_pack
    from oaos2.tasks.plugins.materials_lab import records as R
    pack = load_task_pack("materials_lab", profile="trio")
    schema = pack.actions["measure"].parameters_schema
    assert "prototype_ids" in schema["properties"] and "required" not in schema
    inst = L.generate(1, density=0.2)
    labs = R.LabRecords(inst, {"A": 0, "B": 1, "C": 2}, capacity=480, request_cap=12, rng_seed=1)
    hon = next(p for p in inst.projects.values() if p.ptype == "honest")
    good = labs.register_prototype("A", hon.project_id, hon.witnesses[0])
    other = labs.register_prototype("B", hon.project_id, hon.witnesses[1])  # B's, not granted to A
    for bad_batch in ([good.prototype_id, "p_NOPE"], [good.prototype_id, other.prototype_id],
                      [good.prototype_id, good.prototype_id]):
        with pytest.raises((ValueError, PermissionError)):
            labs.explore_batch("A", bad_batch, 1)
    assert labs.used["A"] == 0 and not labs.records
    with pytest.raises(ValueError):
        labs.explore_batch("A", [good.prototype_id] * 1, 13)
    labs.used["A"] = 475
    with pytest.raises(ValueError):
        labs.explore_batch("A", [good.prototype_id], 6)
    assert labs.used["A"] == 475 and not labs.records
    labs.used["A"] = 0
    recs = labs.explore_batch("A", [good.prototype_id], 3)
    assert len(recs) == 3 and labs.used["A"] == 3


def test_family_scope_restricts_the_pool() -> None:
    """The pilot presets open family Alpha only: the pool's projects, the public listing, and
    a report on another family's project all respect the scope."""
    from oaos2.organizations.loader import load_org_spec
    from oaos2.tasks.plugins.materials_lab.pool import LabPool

    class _Ctx:
        pass

    for preset in ("materials_peers_smoke", "materials_peers", "materials_director"):
        ctx = _Ctx()
        ctx.org_spec = load_org_spec(preset)
        ctx.lc = ctx.org_spec.live_coordination
        pool = LabPool.from_context(ctx)
        assert {p.family for p in pool.inst.projects.values()} == {"alpha"}
        assert set(pool.inst.public["families"]) == {"alpha"}
        assert len(pool.inst.projects) == 3
        rep = pool.records.score("lab_heat", "B1", "p_NONE", {"heat": [], "strength": [], "water": []})
        assert rep.kind == "invalid" and "unknown_project" in rep.reasons
    ctx = _Ctx()
    ctx.org_spec = load_org_spec("materials_trio")
    ctx.lc = ctx.org_spec.live_coordination
    assert len(LabPool.from_context(ctx).inst.projects) == 9


def test_trap_calibration_helpers_reproduce_the_pilot_trap() -> None:
    """The known-feasible control of September 21, 2026 stayed for 69 minutes on a recipe
    one relation short. By enumeration: seed 6 has 25 qualifying recipes on A1 with
    component 0 at every value; that recipe is three single changes from the nearest, and
    every route passes through a worse recipe (barrier 1), while the previous control's
    favorite had a route that never worsens. The setback-tolerant policy stays in budget."""
    import scripts.materials_lab_trap_calibration as T
    from oaos2.tasks.plugins.materials_lab import search as S
    inst = L.generate(6, density=0.2)
    proj = inst.projects["A1"]
    nv, total, qual = T.project_arrays(inst, proj)
    members = np.flatnonzero(qual)
    assert members.size == 25 and int((nv == 0).sum()) >= 25
    assert sorted(set(((members // T.POW[0]) % 4).tolist())) == [0, 1, 2, 3]

    def index(recipe):
        return int((np.array(recipe) * T.POW).sum())

    trap = index([1, 1, 1, 0, 1, 1, 1, 3, 0, 3, 3, 3])
    assert int(nv[trap]) == 1 and T.hamming_to_set(trap, members) == 3
    assert T.barrier(trap, nv, qual) == (1, 3)
    assert T.score_barrier(trap, total, qual) > 0
    earlier = index([1, 1, 1, 3, 1, 1, 3, 1, 1, 3, 1, 3])
    assert T.hamming_to_set(earlier, members) == 2 and T.barrier(earlier, nv, qual) == (0, 2)
    assert T.ascend(trap, total) == trap  # it is a local optimum of the summed means
    ledger = S.setbacks(inst, proj, (0, 1, 2), 300, np.random.default_rng(3))
    assert 290 <= ledger.used <= 300

