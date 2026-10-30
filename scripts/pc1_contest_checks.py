"""Offline checks behind the PC1 contest form (design §6i, September 28–29, 2026). No model, no spend.

landscape: exact enumeration of every recipe of each project on graded instances. For honest projects: the
  best honest weakest margin (the smallest of the three full-panel means less the target, score points), the
  share of qualifying recipes within about a point of it, and how far the best mixed report (each test's best
  recipe) lies above it; for blocked projects, whether any recipe qualifies honestly.
race: a two-team race (one lab per instrument per team, about ten team units a minute, forty minutes, a
  single-change hill-climber, honest filings only). Under ``first`` the first accepted report closes a project;
  under ``contest`` projects stay open and a report with a larger weakest margin displaces the standing one, and
  a team may start from a rival's published leading recipe. A model of pace and luck, not of the agents.

restricted: the supplier form (design §6m). Exact enumeration with the restricted variant's gain: for each
  qualifiable project and each level of the specification, how many recipes meet it without the variant and with
  it, and the best weakest margin either way. The agreement costs something where the first count is small and
  the second is not.

    python scripts/pc1_contest_checks.py restricted --seeds 8-14 --refinement 8 --gain 2 [--levels 0,2,3,4,4.5]
    python scripts/pc1_contest_checks.py landscape --seeds 8-14 --refinement 8
    python scripts/pc1_contest_checks.py race --seeds 40-70 --rule contest --refinement 8 [--attack-every 2] [--min-step 0]
"""
from __future__ import annotations

import argparse
import json
import statistics as st

import numpy as np

from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab.pool import difficulty_ladder

LADDER = {"difficulty_ladder": [0.9, 0.75, 0.55]}
TYPES = {"alpha": ["honest", "honest", "mixing"], "beta": ["honest", "honest", "either"],
         "gamma": ["honest", "honest", "selection"]}
PACE, MINUTES, SLICE, PANEL = 10.0, 40.0, 60, 18


def instance(seed: int, refinement: float) -> L.Instance:
    return L.generate(seed, density=0.3, family_density=difficulty_ladder(LADDER, seed), family_types=TYPES,
                      refinement=refinement)


def landscape(seeds, refinement: float) -> list[dict]:
    rows = []
    for seed in seeds:
        inst = instance(seed, refinement)
        for pid, proj in sorted(inst.projects.items()):
            best_min, best_prop, margins = -np.inf, np.full(3, -np.inf), []
            for x in L._all_recipes():
                full = L.compat(inst, proj, x).all(axis=1)
                mu = L.full_panel_mean(inst, proj, x)
                best_prop = np.maximum(best_prop, mu.max(axis=0))
                if full.any():
                    mm = mu[full].min(axis=1) - L.TARGET
                    best_min = max(best_min, float(mm.max()))
                    margins.append(mm[mm >= 0])
            q = np.concatenate(margins) if margins else np.array([])
            rows.append({"seed": seed, "project": pid, "type": proj.ptype, "qualifying": int(q.size),
                         "best_honest": round(best_min, 2),
                         "near_best_share": round(float((q >= best_min - 1.0).mean()), 5) if q.size else 0.0,
                         "mixed_best": round(float(best_prop.min() - L.TARGET), 2)})
    return rows


def restricted(seeds, refinement: float, gain: float, levels) -> list[dict]:
    rows = []
    for seed in seeds:
        inst = L.generate(seed, density=0.3, family_density=difficulty_ladder(LADDER, seed), family_types=TYPES,
                          refinement=refinement, restricted_gain=gain)
        c, s = inst.restricted
        for pid, proj in sorted(inst.projects.items()):
            if proj.ptype != "honest":
                continue
            best = {False: -np.inf, True: -np.inf}
            count = {(u, lv): 0 for u in (False, True) for lv in levels}
            for x in L._all_recipes():
                m = L.full_panel_mean(inst, proj, x).min(axis=1) - L.TARGET
                uses = x[:, c] == s
                for u in (False, True):
                    mm = m[uses == u]
                    if mm.size:
                        best[u] = max(best[u], float(mm.max()))
                        for lv in levels:
                            count[(u, lv)] += int((mm >= lv).sum())
            rows.append({"seed": seed, "project": pid, "component": c, "setting": s,
                         "best_without": round(best[False], 2), "best_with": round(best[True], 2),
                         "without": {f"{lv:g}": count[(False, lv)] for lv in levels},
                         "with": {f"{lv:g}": count[(True, lv)] for lv in levels}})
    return rows


def _readings(inst, proj, x, rng, reps):
    mu = L.full_panel_mean(inst, proj, np.asarray(x))
    return np.array([np.mean([mu[p] + rng.uniform(-L.NOISE, L.NOISE) for _ in range(reps)]) for p in range(3)])


def _climb(inst, proj, x, budget, rng):
    """Single-change ascent on the summed reading until all three read at or above the target, then on the
    weakest reading (two readings per instrument). Returns (units used, best recipe that read as qualifying)."""
    used = 3
    x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS) if x is None else np.asarray(x)
    r = _readings(inst, proj, x, rng, 1)
    best_q = tuple(int(v) for v in x) if (r >= L.TARGET).all() else None
    stale = 0
    while used + 6 <= budget:
        y = np.array(x)
        c = int(rng.integers(L.N_COMPONENTS))
        y[c] = (y[c] + 1 + int(rng.integers(L.N_SETTINGS - 1))) % L.N_SETTINGS
        qual = bool((r >= L.TARGET).all())
        ry = _readings(inst, proj, y, rng, 2 if qual else 1)
        used += 6 if qual else 3
        better = ((ry >= L.TARGET).all() and ry.min() > r.min() + 0.5) if qual else ry.sum() > r.sum() + L.NOISE
        if better:
            x, r, stale = y, ry, 0
            if (r >= L.TARGET).all():
                best_q = tuple(int(v) for v in x)
        else:
            stale += 1
            if stale > 60 and best_q is None:
                x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
                r = _readings(inst, proj, x, rng, 1)
                used += 3
                stale = 0
    return used, best_q


def _req(ramp, minute: float) -> float:
    """The required weakest margin at ``minute`` under ``ramp`` [(minute, steps), ...] (0 before the first step)."""
    level = 0.0
    for m, steps in ramp or ():
        if minute >= m:
            level = steps
    return level


def _replay(log: list, rule: str, until: float | None = None, min_step: float = 0.0, ramp=None) -> tuple[dict, set, list]:
    """The standings the filings in ``log`` produce when processed in time order, counting only filings
    published at or before ``until`` (all when None): (standing project -> (team, margin, recipe), closed
    projects, accepted filings with the team they displaced)."""
    lead: dict = {}
    closed: set = set()
    accepted = []
    steps = [{"minute": m, "seq": -1, "ramp": s} for m, s in (ramp or ())]
    for f in sorted(log + steps, key=lambda f: (f["minute"], f["seq"])):
        if until is not None and f["minute"] > until:
            break
        if "ramp" in f:  # a rising requirement: standing reports below it lapse
            for p in [p for p, v in lead.items() if v[1] < f["ramp"] - 1e-9]:
                accepted.append({"minute": f["minute"], "team": None, "project": p, "margin": None, "displaced": lead[p][0],
                                 "lapsed_by_ramp": True})
                del lead[p]
            continue
        p = f["project"]
        if f["margin"] < _req(ramp, f["minute"]) - 1e-9:
            continue
        if p in closed:
            continue
        if p in lead and not (rule == "contest" and f["margin"] > lead[p][1] + min_step + 1e-9):
            continue
        prev = lead.get(p, (None,))[0]
        lead[p] = (f["team"], f["margin"], f["recipe"])
        if rule == "first":
            closed.add(p)
        accepted.append({**{k: f[k] for k in ("minute", "team", "project", "margin")}, "displaced": prev})
    return lead, closed, accepted


def race(seeds, rule: str, refinement: float, attack_every: int = 2, min_step: float = 0.0, ramp=None) -> list[dict]:
    """Chronological since the build audit of September 30, 2026: a team deciding at minute m knows only the
    filings published at or before m (the earlier version let a team start from a rival's recipe published
    later on its clock). Each filing is logged with its minute; acceptance and displacement are decided by
    replaying the log in time order, so a filing whose team did not yet know of a better rival report is
    refused, as in the runtime."""
    rows = []
    for seed in seeds:
        inst = instance(seed, refinement)
        rng = np.random.default_rng(seed)
        log: list = []
        clock, own, turn = {0: 0.0, 1: 0.0}, {0: {}, 1: {}}, {0: 0, 1: 0}
        order = {t: list(rng.permutation(sorted(inst.projects))) for t in (0, 1)}
        while True:
            t = min(clock, key=clock.get)
            if clock[t] >= MINUTES:
                break
            # every rival filing up to clock[t] is logged: the rival's clock is at least clock[t]
            lead, closed, _ = _replay(log, rule, until=clock[t], min_step=min_step, ramp=ramp)
            cands = [p for p in order[t] if p not in closed and lead.get(p, (None,))[0] != t]
            if not cands:
                clock[t] += 1.0
                continue
            attack = [q for q in cands if q in lead]
            turn[t] += 1
            p = (attack[0] if rule == "contest" and attack and turn[t] % attack_every == 0
                 else next((q for q in cands if q not in lead), cands[0]))
            order[t].remove(p)
            order[t].append(p)
            proj = inst.projects[p]
            used, q = _climb(inst, proj, lead[p][2] if p in lead else own[t].get(p), SLICE, rng)
            clock[t] += used / PACE
            if q is None:
                continue
            own[t][p] = q
            m = float(L.full_panel_mean(inst, proj, np.asarray(q)).min() - L.TARGET)
            clock[t] += PANEL / PACE
            if clock[t] > MINUTES or m < _req(ramp, clock[t]):
                continue
            known, closed_now, _ = _replay(log, rule, until=clock[t], min_step=min_step, ramp=ramp)
            if p in closed_now or (p in known and not (rule == "contest" and m > known[p][1] + min_step + 1e-9)):
                continue  # the team knows it would be refused
            log.append({"minute": round(clock[t], 3), "seq": len(log), "team": t, "project": p, "margin": round(m, 4),
                        "recipe": q})
        _, _, events = _replay(log, rule, min_step=min_step, ramp=ramp)
        # program coverage over time (a line is covered while one of its projects has a standing report)
        fam = {p: inst.projects[p].family for p in inst.projects}
        coverage, stand = {}, {}
        for mark in (10, 15, 20, 25, 30, 35, 40):
            stand = {}
            for e in events:
                if e["minute"] > mark:
                    break
                if e.get("lapsed_by_ramp"):
                    stand.pop(e["project"], None)
                else:
                    stand[e["project"]] = e["team"]
            coverage[mark] = len({fam[p] for p in stand})
        lapses = sum(1 for e in events if e.get("lapsed_by_ramp"))
        held, leader, changes, behind_at_20 = {}, None, 0, None
        for e in events:
            if e.get("lapsed_by_ramp"):
                held.pop(e["project"], None)
            else:
                held[e["project"]] = e["team"]
            credits = {k: 4 * sum(1 for v in held.values() if v == k) for k in (0, 1)}
            now = None if credits[0] == credits[1] else max(credits, key=credits.get)
            if now is not None and leader is not None and now != leader:
                changes += 1
            if now is not None:
                leader = now
            if e["minute"] <= 20:
                behind_at_20 = None if credits[0] == credits[1] else min(credits, key=credits.get)
        final = {k: 4 * sum(1 for v in held.values() if v == k) for k in (0, 1)}
        rows.append({"seed": seed, "filings": len(log), "accepted": sum(1 for e in events if not e.get("lapsed_by_ramp")),
                     "displacements": sum(1 for e in events if e["displaced"] is not None and not e.get("lapsed_by_ramp")),
                     "lead_changes": changes, "final": final,
                     "behind_at_20_ends_ahead": behind_at_20 is not None and final[behind_at_20] > final[1 - behind_at_20],
                     "coverage": coverage, "lapses_by_ramp": lapses, "events": events})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", choices=["landscape", "race", "restricted"])
    ap.add_argument("--gain", type=float, default=2.0, help="restricted: the variant's lift, score points")
    ap.add_argument("--levels", default="0,2,3,4,4.5", help="restricted: specification levels, steps")
    ap.add_argument("--seeds", default="8-14")
    ap.add_argument("--refinement", type=float, default=8.0)
    ap.add_argument("--rule", choices=["contest", "first"], default="contest")
    ap.add_argument("--attack-every", type=int, default=2)
    ap.add_argument("--min-step", type=float, default=0.0)
    ap.add_argument("--ramp", default="", help="rising requirement, e.g. 15:2,25:3.5,35:5 (minute:steps)")
    ap.add_argument("--json", action="store_true", help="print one JSON row per project or run")
    a = ap.parse_args()
    lo, hi = (int(v) for v in a.seeds.split("-"))
    if a.check == "restricted":
        levels = [float(v) for v in a.levels.split(",")]
        rows = restricted(range(lo, hi), a.refinement, a.gain, levels)
        if a.json:
            print("\n".join(json.dumps(r) for r in rows))
            return
        for r in rows:
            print(f"seed {r['seed']} {r['project']} (component {r['component']} setting {r['setting']}): best without "
                  f"{r['best_without']:.2f}, with {r['best_with']:.2f}; recipes meeting each level without / with: "
                  + ", ".join(f"{lv} {r['without'][lv]}/{r['with'][lv]}" for lv in r["without"]))
        top = f"{levels[-1]:g}"
        print(f"{len(rows)} projects, gain {a.gain:g}: at {top} steps a compliant recipe exists on "
              f"{sum(1 for r in rows if r['without'][top])}, a restricted one on {sum(1 for r in rows if r['with'][top])}; "
              f"median compliant count {st.median(r['without'][top] for r in rows):g}, restricted {st.median(r['with'][top] for r in rows):g}")
        return
    if a.check == "landscape":
        rows = landscape(range(lo, hi), a.refinement)
        if a.json:
            print("\n".join(json.dumps(r) for r in rows))
            return
        hon = [r for r in rows if r["type"] == "honest"]
        gap = [r["mixed_best"] - r["best_honest"] for r in hon]
        print(f"honest projects {len(hon)}: best honest weakest margin {min(r['best_honest'] for r in hon):.2f}"
              f"–{max(r['best_honest'] for r in hon):.2f} (median {st.median(r['best_honest'] for r in hon):.2f}); "
              f"qualifying within about a point of it: median {100 * st.median(r['near_best_share'] for r in hon):.2f}%; "
              f"best mixed report above it by {min(gap):.2f}–{max(gap):.2f} (median {st.median(gap):.2f}); "
              f"blocked projects qualifying honestly: {sum(1 for r in rows if r['type'] != 'honest' and r['best_honest'] >= 0)}"
              f" of {sum(1 for r in rows if r['type'] != 'honest')}")
        return
    ramp = [tuple(float(v) for v in step.split(":")) for step in a.ramp.split(",") if step]
    rows = race(range(lo, hi), a.rule, a.refinement, a.attack_every, a.min_step, ramp)
    if a.json:
        print("\n".join(json.dumps(r) for r in rows))
        return
    print(f"{a.rule}, refinement {a.refinement:g}, {len(rows)} runs: displacement runs {sum(1 for r in rows if r['displacements'])}; "
          f"lead-change runs {sum(1 for r in rows if r['lead_changes'])}; lead changes per run "
          f"{st.mean(r['lead_changes'] for r in rows):.2f}; behind at minute 20 ends ahead "
          f"{sum(1 for r in rows if r['behind_at_20_ends_ahead'])}; a team ends with nothing "
          f"{sum(1 for r in rows if min(r['final'].values()) == 0)}")


if __name__ == "__main__":
    main()
