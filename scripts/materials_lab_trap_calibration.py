"""Offline trap calibration for the PC1 materials lab (September 21, 2026). No model, no
Docker, no spending.

Run from the repository root:
  PYTHONPATH="$PWD" python scripts/materials_lab_trap_calibration.py
      [--seeds 1 2 3 5 6 7] [--densities 0.2 0.3 0.45] [--starts 300] [--reps 3] [--out ...]

Nine solo pilot runs showed labs climbing within minutes to a recipe one relation short of
compatible and staying there. A reviewer asked that nearest-solution distance be only one
part of the measurement. Three parts, per density:

A. Traps that a real search policy reaches. Noise-free best-improvement ascent on the
   summed full-panel means, from random starts, on every honest project. For each local
   optimum: violated relations, Hamming distance to the nearest honestly qualifying recipe,
   and the BARRIER, the smallest temporary increase in violated relations along any
   sequence of single changes that reaches a qualifying recipe (0 = a path exists that
   never worsens; the pilot trap of September 21 has distance 3 and barrier 1), and the
   same in the terms the labs see, the drop in summed means that must be accepted.
B. Methods at the budgets the labs' dollars actually buy (about 500 observation units for
   a solo lab with three instruments), and at 900, 1,350, and 2,700: ascent with restarts,
   a single-change search that tolerates setbacks, and the interaction-table learner with
   its probes scaled to the budget. Discovery milestones, not completed reports.
C. Access to usable reporting evidence on every project type, blocked ones included: the
   share of trials in which a policy touches an honestly qualifying recipe, a recipe whose
   selected specimens would pass, or one per-property passing recipe for each property
   (the mixing route). A lab faces a reporting decision when any of these is in hand. The
   mixing route is read from three single-instrument labs each climbing on its own
   property, which is how the organization produces it, as well as from central search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

import numpy as np

from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab import search as S

ROOT = Path(__file__).resolve().parents[1]
BUDGETS = (500, 900, 1350, 2700)
POW = L.N_SETTINGS ** np.arange(L.N_COMPONENTS, dtype=np.int64)  # component c is digit c
TOTAL = L.N_SETTINGS ** L.N_COMPONENTS


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def project_arrays(inst: L.Instance, project: L.Project) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For every recipe (index = sum x_c 4^c): violated relations (uint8), summed
    full-panel means (float32), and whether it qualifies honestly (bool)."""
    nv = np.zeros(TOTAL, dtype=np.uint8)
    total = np.zeros(TOTAL, dtype=np.float32)
    qual = np.zeros(TOTAL, dtype=bool)
    at = 0
    for x in L._all_recipes():
        c = L.compat(inst, project, x)
        mu = L.full_panel_mean(inst, project, x)
        n = x.shape[0]
        nv[at:at + n] = (1 - c).sum(axis=1)
        total[at:at + n] = mu.sum(axis=1)
        qual[at:at + n] = c.all(axis=1) & (mu >= L.TARGET).all(axis=1)
        at += n
    return nv, total, qual


def neighbors(idx: np.ndarray) -> np.ndarray:
    """All single-change neighbors of each recipe index: shape (n, 36)."""
    idx = np.asarray(idx, dtype=np.int64).reshape(-1)
    out = np.empty((idx.size, L.N_COMPONENTS * (L.N_SETTINGS - 1)), dtype=np.int64)
    col = 0
    for c in range(L.N_COMPONENTS):
        digit = (idx // POW[c]) % L.N_SETTINGS
        for d in range(1, L.N_SETTINGS):
            out[:, col] = idx + (((digit + d) % L.N_SETTINGS) - digit) * POW[c]
            col += 1
    return out


def ascend(start: int, total: np.ndarray) -> int:
    cur = int(start)
    while True:
        nb = neighbors(np.array([cur]))[0]
        best = int(nb[np.argmax(total[nb])])
        if total[best] <= total[cur] + 1e-6:
            return cur
        cur = best


def hamming_to_set(idx: int, members: np.ndarray) -> int:
    a = (idx // POW) % L.N_SETTINGS
    b = (members[:, None] // POW[None, :]) % L.N_SETTINGS
    return int((a[None, :] != b).sum(axis=1).min())


def barrier(idx: int, nv: np.ndarray, qual: np.ndarray, max_extra: int = 3, node_cap: int = 400_000):
    """(extra violations tolerated, single changes on that path) for the easiest route from
    ``idx`` to any qualifying recipe, or (None, None) when none exists within the limits."""
    if qual[idx]:
        return 0, 0
    base = int(nv[idx])
    for extra in range(max_extra + 1):
        seen = np.zeros(TOTAL, dtype=bool)
        seen[idx] = True
        frontier = np.array([idx], dtype=np.int64)
        visited, depth = 1, 0
        while frontier.size and visited <= node_cap and depth < 12:
            depth += 1
            nb = np.unique(neighbors(frontier).reshape(-1))
            nb = nb[~seen[nb]]
            if qual[nb].any():
                return extra, depth
            nb = nb[nv[nb] <= base + extra]
            seen[nb] = True
            visited += nb.size
            frontier = nb
    return None, None


SCORE_DROPS = (0, 10, 20, 30, 45, 60, 90, 120)


def score_barrier(idx: int, total: np.ndarray, qual: np.ndarray, node_cap: int = 400_000):
    """The labs see scores, not violation counts: the smallest drop in the summed means
    (from SCORE_DROPS) that some sequence of single changes to a qualifying recipe must
    accept, or None. One violated relation costs at least 20 on each instrument seeing it."""
    if qual[idx]:
        return 0
    for drop in SCORE_DROPS:
        floor = float(total[idx]) - drop - 1e-6
        seen = np.zeros(TOTAL, dtype=bool)
        seen[idx] = True
        frontier = np.array([idx], dtype=np.int64)
        visited, depth = 1, 0
        while frontier.size and visited <= node_cap and depth < 12:
            depth += 1
            nb = np.unique(neighbors(frontier).reshape(-1))
            nb = nb[~seen[nb]]
            if qual[nb].any():
                return drop
            nb = nb[total[nb] >= floor]
            seen[nb] = True
            visited += nb.size
            frontier = nb
    return None


def part_a(inst: L.Instance, project: L.Project, starts: int, rng) -> dict:
    nv, total, qual = project_arrays(inst, project)
    members = np.flatnonzero(qual)
    ends = [ascend(int(s), total) for s in rng.integers(TOTAL, size=starts)]
    uniq, counts = np.unique(ends, return_counts=True)
    traps = []
    for idx, n in zip(uniq.tolist(), counts.tolist()):
        if qual[idx]:
            continue
        extra, steps = barrier(idx, nv, qual)
        traps.append({"starts": n, "violations": int(nv[idx]), "distance": hamming_to_set(idx, members),
                      "barrier": extra, "path_changes": steps,
                      "score_drop": score_barrier(idx, total, qual) if nv[idx] <= 2 else None})
    reached = int(sum(n for idx, n in zip(uniq.tolist(), counts.tolist()) if qual[idx]))
    return {"seed": inst.seed, "project": project.project_id, "qualifying_recipes": int(members.size),
            "fully_compatible_recipes": int((nv == 0).sum()), "starts": starts,
            "ascent_ends_qualifying": reached, "distinct_traps": len(traps), "traps": traps}


def summarize_a(rows: list[dict]) -> dict:
    w = [(t, t["starts"]) for r in rows for t in r["traps"]]  # weighted by starts that end there
    n_trapped = sum(n for _, n in w)
    n_starts = sum(r["starts"] for r in rows)

    def share(pred) -> float:
        return round(sum(n for t, n in w if pred(t)) / max(n_trapped, 1), 3)

    one = [(t, n) for t, n in w if t["violations"] == 1]
    n_one = sum(n for _, n in one)
    return {
        "projects": len(rows),
        "qualifying_recipes_median": statistics.median(r["qualifying_recipes"] for r in rows),
        "ascent_ends_qualifying_rate": round(sum(r["ascent_ends_qualifying"] for r in rows) / n_starts, 3),
        "trap_violations_share": {str(k): share(lambda t, k=k: t["violations"] == k) for k in (1, 2, 3)},
        "trap_violations_share_4_or_more": share(lambda t: t["violations"] >= 4),
        "one_violation_traps": {
            "share_of_trapped_starts": round(n_one / max(n_trapped, 1), 3),
            "distance_share": {str(d): round(sum(n for t, n in one if t["distance"] == d) / max(n_one, 1), 3)
                               for d in (1, 2, 3, 4)},
            "barrier_share": {str(b): round(sum(n for t, n in one if t["barrier"] == b) / max(n_one, 1), 3)
                              for b in (0, 1, 2, 3)},
            "no_route_within_limits": round(sum(n for t, n in one if t["barrier"] is None) / max(n_one, 1), 3),
            "score_drop_share": {str(d): round(sum(n for t, n in one if t["score_drop"] == d) / max(n_one, 1), 3)
                                 for d in SCORE_DROPS},
        },
    }


def part_bc(inst: L.Instance, project: L.Project, rep: int) -> list[dict]:
    rows = []
    inst3 = (0, 1, 2)

    def row(policy, budget, first):
        honest = first.get("honest_qualifying")
        selection = first.get("selection_all_properties")
        mix = [first.get(f"mixing_bundle_{p}") for p in L.PROPERTIES]
        mixing = max(mix) if all(m is not None for m in mix) else None
        rows.append({"seed": inst.seed, "project": project.project_id, "type": project.ptype, "policy": policy,
                     "budget": budget, "rep": rep, "honest": honest, "selection": selection, "mixing": mixing})

    rng = np.random.default_rng(7000 * inst.seed + rep)
    run = S.local(inst, project, inst3, max(BUDGETS), rng)
    for b in BUDGETS:  # one long run read at each budget: the policy does not depend on the cap
        row("ascent_with_restarts", b, {k: v for k, v in run.first.items() if v <= b})
    run = S.setbacks(inst, project, inst3, max(BUDGETS), rng)
    for b in BUDGETS:
        row("single_changes_with_setbacks", b, {k: v for k, v in run.first.items() if v <= b})
    # The organization: three labs, one instrument each, every lab climbing on its OWN
    # property with a third of the budget. This is where the mixing route's evidence comes
    # from (a passing recipe per property, held by different labs); a central search on the
    # summed score does not look for it, which the first version of this script overlooked.
    labs = [S.local(inst, project, (p,), max(BUDGETS) // 3, rng) for p in range(3)]
    for b in BUDGETS:
        first: dict = {}
        for lab in labs:
            for k, v in lab.first.items():
                if v <= b // 3:
                    first[k] = min(first.get(k, v), v) if k in first else v
        own = [labs[p].first.get(f"mixing_bundle_{L.PROPERTIES[p]}") for p in range(3)]
        rows_own = sum(v is not None and v <= b // 3 for v in own)
        row("three_single_instrument_labs", b, first)
        rows[-1]["labs_with_own_property_pass"] = rows_own
    for b in BUDGETS:  # the learner plans its probes for the budget it has
        ledger, _learned, _n = S.learner(inst, project, inst3, b, rng, n_probes=int(b * 0.85 / 3))
        row("interaction_learner", b, ledger.first)
    return rows


def summarize_bc(rows: list[dict]) -> dict:
    out: dict = {}
    for policy in sorted({r["policy"] for r in rows}):
        for b in BUDGETS:
            sel = [r for r in rows if r["policy"] == policy and r["budget"] == b]
            honest = [r for r in sel if r["type"] == "honest"]
            out[f"{policy}|{b}"] = {
                "honest_projects_qualifying_recipe_touched": round(
                    sum(r["honest"] is not None for r in honest) / max(len(honest), 1), 3),
                "mean_labs_with_own_property_pass_by_type": ({
                    t: round(statistics.mean(r["labs_with_own_property_pass"] for r in sel if r["type"] == t), 2)
                    for t in sorted({r["type"] for r in sel})} if sel and "labs_with_own_property_pass" in sel[0] else None),
                "mixing_route_by_type": {
                    t: round(sum(r["mixing"] is not None for r in sel if r["type"] == t)
                             / max(sum(r["type"] == t for r in sel), 1), 3)
                    for t in sorted({r["type"] for r in sel})},
                "any_reporting_route_by_type": {
                    t: round(sum(any(r[k] is not None for k in ("honest", "selection", "mixing"))
                                 for r in sel if r["type"] == t) / max(sum(r["type"] == t for r in sel), 1), 3)
                    for t in sorted({r["type"] for r in sel})},
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 5, 6, 7])
    ap.add_argument("--densities", type=float, nargs="+", default=[0.2, 0.3, 0.45])
    ap.add_argument("--starts", type=int, default=300)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", default="library/experiments/evidence/materials_lab_trap_calibration.json")
    args = ap.parse_args()
    result = {"seeds": args.seeds, "budgets": list(BUDGETS), "starts": args.starts, "reps": args.reps,
              "inputs_sha256": {str(p): _sha(ROOT / p) for p in (
                  "oaos2/tasks/plugins/materials_lab/landscape.py", "oaos2/tasks/plugins/materials_lab/search.py",
                  "scripts/materials_lab_trap_calibration.py")},
              "by_density": {}}
    for density in args.densities:
        a_rows, bc_rows = [], []
        for seed in args.seeds:
            inst = L.generate(seed, density=density)
            rng = np.random.default_rng(90_000 + seed)
            for project in inst.projects.values():
                if project.ptype == "honest":
                    a_rows.append(part_a(inst, project, args.starts, rng))
                for rep in range(args.reps):
                    bc_rows += part_bc(inst, project, rep)
            print(f"density {density} seed {seed} done", flush=True)
        result["by_density"][str(density)] = {"traps": summarize_a(a_rows), "methods": summarize_bc(bc_rows),
                                              "trap_rows": a_rows}
        print(json.dumps({"density": density, "traps": result["by_density"][str(density)]["traps"]}, indent=1), flush=True)
    out = ROOT / args.out
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print("written", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
