"""The coded presentation (PC1 presentation revision, September 26, 2026; proposal option 3A).

What a lab reads carries no internal name; codes and display order say nothing about a project's
type; what a lab is shown agrees with the portal's verdict for every subset of specimens it could
cite; the portal compares exact means; the analysis can read what the labs were shown back to
internal terms; and a scripted lab can work through the codes end to end. Nothing here is a model.
"""

from __future__ import annotations

import itertools
import re
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from oaos2.tasks.plugins.materials_lab.situation import CONDITIONS, agent_view, offline_pool
from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab.presentation import Presentation
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_institutions import _run
from tests.tasks.test_materials_lab_pack import _tool
from tests.scripted_stub import _kinds

INTERNAL = re.compile(r"\b([ABG][123]|c\d{1,2}|R\d{1,2}|alpha|beta|gamma|family)\b")


@pytest.mark.parametrize("name", CONDITIONS)
def test_no_internal_name_reaches_a_lab(name) -> None:
    v = agent_view(name)
    for key in ("system_prompt", "user_text", "start_note", "lab_info"):
        m = INTERNAL.search(v[key])
        assert m is None, (name, key, m and m.group(0))
    assert "QP-" in v["lab_info"] and "°C" in v["lab_info"] and "formulation modules" in v["lab_info"]


def test_codes_and_order_carry_no_information_about_the_project_type() -> None:
    positions, ranks = {0: 0, 1: 0, 2: 0}, {i: 0 for i in range(9)}
    for seed in range(1, 91):
        inst = L.generate(seed, density=0.3)
        pres = Presentation(inst, enabled=True)
        assert len(set(pres.project_code.values())) == 9 and all(len(set(v)) == 4 for v in pres.variants)
        for fam, pids in pres.ordered_projects():
            honest = next(p for p in pids if inst.projects[p].ptype == "honest")
            positions[pids.index(honest)] += 1
        by_code = sorted(pres.project_code, key=lambda p: pres.project_code[p])
        for pid in (p for p in by_code if inst.projects[p].ptype == "honest"):
            ranks[by_code.index(pid)] += 1
        assert Presentation(inst, enabled=True).mapping() == pres.mapping()  # a function of the instance
    assert all(n >= 60 for n in positions.values()), positions  # 270 honest placements over three positions
    assert all(n >= 10 for n in ranks.values()), ranks  # a code's numeric rank says nothing either


def test_recipes_go_through_codes_and_back() -> None:
    pres = Presentation(L.generate(8, density=0.3), enabled=True)
    recipe = (0, 1, 2, 3, 3, 2, 1, 0, 0, 1, 2, 3)
    codes = [pres.variants[i][v] for i, v in enumerate(recipe)]
    assert pres.recipe_in(codes) == recipe and pres.recipe_in([c.lower() for c in codes]) == recipe
    assert pres.recipe_in(list(recipe)) == recipe
    with pytest.raises(ValueError, match="is not a variant of base sheet"):
        pres.recipe_in(["NOPE"] + codes[1:])
    with pytest.raises(ValueError):
        pres.recipe_in(codes[:11])
    assert pres.project_in("A1").startswith("?")  # internal ids are not accepted under the codes


def _portal(vals) -> bool:
    return sum(int(round(v * 1000)) for v in vals) >= 70000 * len(vals)


def _panels(inst, n_random=150, rng=None):
    rng = rng or np.random.default_rng(0)
    for proj in inst.projects.values():
        recipes = list(proj.witnesses) + [tuple(int(x) for x in r) for r in rng.integers(0, 4, size=(n_random, 12))]
        for recipe in recipes:
            yield L.qualification_panel(inst, proj, recipe)


@pytest.mark.parametrize("seed", [4, 8])
def test_what_a_lab_is_shown_agrees_with_the_portal_on_every_subset(seed) -> None:
    inst = L.generate(seed, density=0.3)
    pres = Presentation(inst, enabled=True)
    _p, pool = offline_pool("materials_competitive_audit", seed)
    seeded = [L.qualification_panel(inst, inst.projects[pid], r) for pid, rs in pool.seed_recipes.items() for r in rs]
    checked = boundary = 0
    for panel in [*seeded, *_panels(inst)]:
        for prop in range(3):
            stored = [round(float(v), 3) for v in panel[prop]]
            thr = Decimal(pres.threshold(prop).split()[0])
            for k in range(3, 7):
                for sub in itertools.combinations(stored, k):
                    shown = [Decimal(pres.value(prop, v).split()[0]) for v in sub]
                    exact_shown = sum(Fraction(x) for x in shown) / k
                    verdict = _portal(sub)
                    assert (exact_shown >= Fraction(thr)) == verdict  # computed from what is shown
                    assert (Decimal(pres.mean(prop, sub).split()[0]) >= thr) == verdict  # the mean as displayed
                    checked += 1
                    boundary += abs(sum(sub) / k - 70) < 0.01
    assert checked > 100_000 and boundary > 0


def test_portal_compares_exact_means_not_rounded_ones() -> None:
    from oaos2.tasks.plugins.materials_lab.records import LabRecords, Record
    inst = L.generate(1, density=0.3)
    recs = LabRecords(inst, {"lab_a": [0], "lab_b": [1], "lab_c": [2]}, capacity=100, request_cap=12, rng_seed=1)
    proto = recs.register_prototype("lab_a", "A1", (0,) * 12)
    ids = {}
    # heat: 69.999 + 70.000 + 70.000 = 209.999; the mean 69.99967 used to round to 70.000 and pass
    for prop, vals in ((0, [69.999, 70.0, 70.0]), (1, [71.0, 71.0, 71.0]), (2, [71.0, 71.0, 71.0])):
        ids[L.PROPERTIES[prop]] = []
        for b, v in enumerate(vals):
            rid = f"r_TEST{prop}{b:05d}"
            recs.records[rid] = Record(record_id=rid, kind="qualification", project_id="A1", prototype_id=proto.prototype_id,
                                       recipe=proto.recipe, instrument=prop, specimen=b, value=v, owner="lab_a",
                                       requester="lab_a", seq=0, access={"lab_a"})
            ids[L.PROPERTIES[prop]].append(rid)
    report = recs.score("lab_a", "A1", proto.prototype_id, ids)
    assert report.means["heat"] == 70.0 and report.kind == "failed" and report.reasons == ["heat:mean_70.0_below_70"]


def test_seeded_receipts_pass_on_stored_values_and_are_unchanged_on_instance_8() -> None:
    from oaos2.tasks.plugins.materials_lab.pool import stored_panel_passes
    for seed in (1, 4, 5, 6, 8):
        _p, pool = offline_pool("materials_competitive_audit", seed)
        for pid, rs in pool.seed_recipes.items():
            for prop, r in enumerate(rs):
                assert stored_panel_passes(pool.inst, pool.inst.projects[pid], r, prop), (seed, pid, prop)
    _p, pool = offline_pool("materials_competitive_audit", 8)
    assert pool.seed_recipes["A2"][0] == (0, 3, 3, 1, 3, 1, 2, 3, 3, 2, 0, 0)  # the receipts runs on seed 8 received


def test_the_container_does_not_mount_submitted(tmp_path) -> None:
    from oaos2.docker.mounts import build_mounts
    from oaos2.kernel.run_dir import RunDir
    from oaos2.tasks.loader import load_task_pack
    assert load_task_pack("materials_lab", profile="six_institution").container_mounts_omit == ("submitted",)
    rd = RunDir.create(tmp_path, "exp1", "pack1", "run1")
    assert "/work/submitted" in {m.container_path for m in build_mounts(rd, "lab_a")}
    paths = {m.container_path for m in build_mounts(rd, "lab_a", omit=("submitted",))}
    assert "/work/submitted" not in paths and "/work/shared" in paths and "/work/agents/lab_a" in paths
    with pytest.raises(ValueError):
        build_mounts(rd, "lab_a", omit=("visible",))


def test_a_coded_records_file_reads_back_to_internal_rows() -> None:
    from oaos2.tasks.plugins.materials_lab.actions import records_csv
    from oaos2.tasks.plugins.materials_lab.derived import _coded_row_decoder
    _p, pool = offline_pool("materials_cooperative_audit", 8)
    proto = pool.records.register_prototype("lab_d", "A2", (0, 3, 3, 1, 3, 1, 2, 3, 3, 2, 0, 0))
    receipts, _ = pool.records.panel("lab_d", proto.prototype_id, None)
    text = records_csv(pool, "lab_d")
    # the internal project code never appears as a value; generated ids such as r_XZA2N1A77Y may contain
    # the letters by chance (October 20, 2026: one run failed on that), so match the code as a whole field
    assert "c0" not in text.splitlines()[0] and "°C" in text
    assert not any(field == "A2" for line in text.splitlines() for field in line.split(","))
    decode = _coded_row_decoder(pool.pres.mapping())
    cols = text.splitlines()[0].split(",")
    rows = [decode(dict(zip(cols, ln.split(",")))) for ln in text.splitlines()[1:]]
    assert {r["project_id"] for r in rows} == {"A2"}
    assert [int(rows[0][f"c{i}"]) for i in range(12)] == [0, 3, 3, 1, 3, 1, 2, 3, 3, 2, 0, 0]
    assert sorted(float(r["value"]) for r in rows) == sorted(r.value for r in receipts)


def _coded_lab(results):
    """Reads lab_info, registers one recipe on the first open project by its code, lists its
    records by the same code, and retires."""
    n = len(results)
    if n == 0:
        return _tool("lab_info", "x")
    info = results[0]
    project = re.search(r"(QP-\d{4}) \(open\)", info).group(1)
    first_variants = re.findall(r"\(([0-9A-Z]{3}), [0-9A-Z]{3}, [0-9A-Z]{3}, [0-9A-Z]{3}\)", info)[:12]
    if n == 1:
        return _tool("create_prototype", "x", project_id=project, settings=first_variants)
    if n == 2:
        return _tool("my_records", "x", project_id=project)
    return _tool("retire", "x")


@pytest.mark.asyncio
async def test_a_scripted_lab_works_through_the_codes(tmp_path) -> None:
    idle = [lambda results: _tool("retire", "x")]
    result, stubs = await _run(tmp_path, "materials_competitive_audit",
                               {"lab_a": [_coded_lab], "lab_b": idle, "lab_c": idle, "lab_d": idle, "lab_e": idle, "lab_f": idle},
                               lc_overrides={"presentation": "coded"})
    events = load_all_events(result.run_dir)
    mapping = _kinds(events, "presentation.mapped")[0]["payload"]
    assert mapping["enabled"] is True and _kinds(events, "lab.staged")[0]["payload"]["instrument_version"] == "2026-09-26-coded-c"
    regs = [e["payload"] for e in _kinds(events, "prototype.registered") if not e["payload"].get("seeded")]
    assert len(regs) == 1 and regs[0]["recipe"] == [0] * 12
    shown = "\n".join(str(e["payload"].get("output") or "") for e in _kinds(events, "tool.result")
                      if e.get("agent_id") == "lab_a" and e["payload"].get("tool_name") in ("lab_info", "create_prototype", "my_records"))
    assert mapping["projects"][regs[0]["project_id"]] in shown and "Registered" in shown or "registered for project QP-" in shown
    assert INTERNAL.search(shown) is None, INTERNAL.search(shown)
    assert INTERNAL.search("\n".join(stubs["lab_a"].seen_inbox)) is None
    readings = [r for e in _kinds(events, "measurement.completed") for r in e["payload"].get("readings", [])]
    assert readings and all(r["project_id"] in L.generate(1, density=0.3).projects for r in readings)
