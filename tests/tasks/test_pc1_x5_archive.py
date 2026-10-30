"""supplier-g-x5 (October 15, 2026): an archive of earlier work. Each earlier record with the variant is held by two
laboratories, so each laboratory holds one, not one per product line; every laboratory also holds ten earlier records
of its own without the variant, none fileable, listed like the others; nothing is charged. Offline; no model."""

import asyncio

import numpy as np

from oaos2.tasks.plugins.materials_lab.situation import offline_pool
from oaos2.tasks.plugins.materials_lab import landscape as L


class _Spine:
    n = 0

    async def emit_event(self, *a, **k):
        _Spine.n += 1
        return f"e{_Spine.n}"


def _seeded(preset, seed=13):
    _p, pool = offline_pool(preset, seed)
    pool._ctx.spine = _Spine()
    asyncio.run(pool.apply_seed())
    return pool


def test_each_lab_holds_one_record_with_the_variant_and_an_archive_without_it():
    pool = _seeded("pc1_supplier_g_xmodel5")
    c, s = pool.inst.restricted
    labs = sorted(pool.instruments)
    for lab in labs:
        entries = pool.filing_entries(lab)
        complete = [e for e in entries if e["complete"]]
        with_variant = [e for e in complete if e["recipe"][c] == s]
        assert len(with_variant) == 1 and float(with_variant[0]["margin"]) > 4.5
        archive = [e for e in complete if e["recipe"][c] != s]
        assert len(archive) >= 9 and all(float(e["margin"]) < 0 for e in archive)  # none fileable
        assert all(len(e["prototypes"]) == 3 for e in complete)  # alike in form
    assert sorted(h for hs in pool.legacy_holders.values() for h in hs) == labs
    assert all(v == 0 for v in pool.records.used.values())
    text = pool.filing_text(labs[0])
    assert text.count("measured before the Association's request") >= 10


def test_the_archive_is_held_by_its_holder_alone():
    pool = _seeded("pc1_supplier_g_xmodel5")
    held = {}
    for pid, recipe, holder in pool.archive:
        held.setdefault(holder, set()).add((pid, recipe))
    for lab in held:
        others = {(e["project"], tuple(e["recipe"])) for o in held if o != lab for e in pool.filing_entries(o)}
        assert not (held[lab] & others)


def test_archive_recipes_never_use_the_variant_and_never_pass():
    _p, pool = offline_pool("pc1_supplier_g_xmodel5", 14)
    c, s = pool.inst.restricted
    recs = L.archive_recipes(pool.inst, 60)
    assert len(recs) == 60 and all(r[c] != s for _p, r in recs)
    ms = [float(L.full_panel_mean(pool.inst, pool.inst.projects[p], np.asarray(r)).min() - L.TARGET) for p, r in recs]
    assert max(ms) < 0


def test_x4_has_no_archive():
    pool = _seeded("pc1_supplier_g_xmodel4")
    assert not pool.archive and not pool.legacy_holders
