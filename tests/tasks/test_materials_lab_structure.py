"""Problem structure in the materials-lab generator (October 9, 2026, T1 design). The
"mixed" default stays byte-identical to the instrument PC1 uses; "decomposable" and
"coupled" share one visibility pattern and differ only in which components a relation
joins; modular search succeeds on a decomposable instance."""
from __future__ import annotations

import hashlib
import itertools
import json

import numpy as np
import pytest

from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab import search as S

# fingerprints of generate(seed, density) taken before the structure option existed
_MIXED = {(1, 0.2): "54f618b613aff99a", (4, 0.3): "ec585ded2549c5ea", (6, 0.2): "b991b223a4af659a"}


def _fingerprint(inst) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(inst.public, sort_keys=True).encode())
    h.update(json.dumps(inst.triples).encode())
    for pid in sorted(inst.projects):
        p = inst.projects[pid]
        h.update(p.tables.tobytes())
        h.update(p.weights.tobytes())
        h.update(json.dumps(p.witnesses).encode())
    for f in sorted(inst.spec_tables):
        h.update(inst.spec_tables[f].tobytes())
    return h.hexdigest()[:16]


@pytest.mark.parametrize("seed,density", sorted(_MIXED))
def test_the_mixed_default_is_unchanged(seed, density) -> None:
    inst = L.generate(seed, density=density)
    assert inst.structure == "mixed" and (inst.visibility == L.VISIBILITY).all()
    assert _fingerprint(inst) == _MIXED[(seed, density)]


def test_the_two_structures_share_visibility_and_differ_in_what_relations_join() -> None:
    d_triples, d_vis = L.structured_layout("decomposable")
    c_triples, c_vis = L.structured_layout("coupled")
    assert (d_vis == c_vis).all() and d_vis.sum(axis=1).tolist() == [4, 4, 4] and (d_vis.sum(axis=0) == 1).all()
    block_of = {c: p for p, cs in L.BLOCKS.items() for c in cs}
    for k, t in enumerate(d_triples):
        assert {block_of[c] for c in t} == {k % 3}   # within the block of the instrument that sees it
    for t in c_triples:
        assert sorted(block_of[c] for c in t) == [0, 1, 2]   # one component of each block
    assert max(len(set(a) & set(b)) for a, b in itertools.combinations(c_triples, 2)) == 1
    for triples in (d_triples, c_triples):
        assert np.bincount([c for t in triples for c in t], minlength=L.N_COMPONENTS).tolist() == [3] * 12
    with pytest.raises(ValueError):
        L.structured_layout("mixed")


def test_a_structured_instance_carries_its_layout_into_the_diagram_and_weights() -> None:
    inst = L.generate(4, density=0.3, structure="coupled")
    assert inst.structure == "coupled" and inst.triples == L.structured_layout("coupled")[0]
    for k, rel in enumerate(inst.public["relations"]):
        assert rel["seen_by"] == [L.PROPERTIES[k % 3]]
    for p in inst.projects.values():
        assert ((p.weights > 0) == (inst.visibility > 0)).all()
        assert all(L.compat(inst, p, np.asarray(w)).all() for w in p.witnesses)


def test_modular_search_assembles_a_compatible_recipe_on_a_decomposable_instance() -> None:
    inst = L.generate(1, density=0.3, structure="decomposable")
    r = S.modular(inst, inst.projects["A1"], 900, np.random.default_rng(0), rounds=1)
    assert r["found_full_compatible"] and r["final_violations"] == 0 and r["per_lab_used"] == [256] * 3


def test_the_nearly_decomposable_layout_has_three_crossing_relations() -> None:
    triples, vis = L.structured_layout("nearly_decomposable")
    block_of = {c: p for p, cs in L.BLOCKS.items() for c in cs}
    crossing = [k for k, t in enumerate(triples) if len({block_of[c] for c in t}) > 1]
    assert crossing == [9, 10, 11] and (vis == L.EXCLUSIVE_VISIBILITY).all()
    assert triples[:9] == L.structured_layout("decomposable")[0][:9]
    assert np.bincount([c for t in triples for c in t], minlength=L.N_COMPONENTS).tolist() == [3] * 12
    inst = L.generate(2, density=0.36, structure="nearly_decomposable")
    r = S.task_force(inst, inst.projects["A1"], 900, np.random.default_rng(0))
    assert r["crossing_relations"] == 3 and r["total_used"] <= 2700


def test_the_interface_layout_routes_every_crossing_relation_through_the_free_components() -> None:
    triples, vis = L.structured_layout("interface")
    block_of = {c: p for p, cs in L.BLOCKS.items() for c in cs}
    crossing = [t for t in triples if len({block_of[c] for c in t}) > 1]
    assert crossing == [L.FREE] * 3 and (vis[:, 9:] == np.eye(3, dtype=np.int8)).all()
    for k in range(9):
        assert {block_of[c] for c in triples[k]} == {k % 3}
    inst = L.generate(3, density=0.33, structure="interface")
    r = S.interface_task_force(inst, inst.projects["A1"], 900, np.random.default_rng(1))
    assert r["interface"] == list(L.FREE) and r["rounds"] >= 1 and max(r["per_lab_used"]) <= 900
