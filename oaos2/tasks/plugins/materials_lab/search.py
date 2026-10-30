"""Algorithmic search baselines for the materials lab (proposal §5.1, plan phase 3).

Each policy sees only what a participant could see: noisy exploratory readings from the
instruments it holds, the public diagram, and its own observations. Ground truth is
consulted only to RECORD when a policy first touched a recipe of each kind (fully
compatible; visibly compatible on an instrument; one that would pass a property's
mixing bundle; one whose best three specimens would pass everywhere). Those first-touch
costs bound what any policy of that class could achieve within a budget.

Policies:
- ``uniform``: random recipes, probed on every held instrument.
- ``local``: hill climbing over single-component changes on the summed noisy score of
  the held instruments, with random restarts on a plateau.
- ``structured``: block coordinate descent over the public relation triples: sweep one
  relation's 64 settings on an instrument that sees it, keep the best, move on. Uses
  the diagram; learns nothing about relations no held instrument sees.
- ``coordinated``: three single-instrument labs run one block coordinate descent
  together, each relation swept by a lab that sees it and charged to that lab, from a
  shared recipe. This is the central investigator emulated by distributed investigators
  who exchange their current best recipe and sweep results; no lab can do it alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from oaos2.tasks.plugins.materials_lab import landscape as L


@dataclass
class Ledger:
    """Observation accounting for one lab or a central investigator. A ``parent``
    ledger (the organization's total) mirrors every charge and milestone, so a
    distributed policy reports first-touch costs in total units as well as per lab."""
    cap: int
    used: int = 0
    first: dict = field(default_factory=dict)  # milestone -> units used when first reached
    parent: "Ledger | None" = None

    def charge(self, n: int = 1) -> bool:
        if self.used + n > self.cap:
            return False
        self.used += n
        if self.parent is not None:
            self.parent.used += n
        return True

    def mark(self, milestone: str) -> None:
        self.first.setdefault(milestone, self.used)
        if self.parent is not None:
            self.parent.mark(milestone)


def _milestones(inst: L.Instance, project: L.Project, x: np.ndarray, ledger: Ledger) -> None:
    c = L.compat(inst, project, x)
    mu = L.full_panel_mean(inst, project, x)
    if c.all():
        ledger.mark("full_compatible")
    for p in range(3):
        if ((1 - c) * inst.visibility[p]).sum() == 0:
            ledger.mark(f"visible_compatible_{L.PROPERTIES[p]}")
        if mu[p] >= L.TARGET:
            ledger.mark(f"mixing_bundle_{L.PROPERTIES[p]}")
    if (mu + L.top3_mean(project.offsets) >= L.TARGET).all():
        ledger.mark("selection_all_properties")
    if (mu >= L.TARGET).all():
        ledger.mark("honest_qualifying")


def _probe(inst, project, x, prop, ledger, rng) -> float | None:
    if not ledger.charge(1):
        return None
    return L.explore(inst, project, tuple(int(v) for v in x), prop, rng)


def uniform(inst, project, instruments: tuple[int, ...], cap: int, rng) -> Ledger:
    ledger = Ledger(cap)
    while ledger.used + len(instruments) <= cap:
        x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
        for p in instruments:
            _probe(inst, project, x, p, ledger, rng)
        _milestones(inst, project, x, ledger)
    return ledger


def local(inst, project, instruments: tuple[int, ...], cap: int, rng) -> Ledger:
    ledger = Ledger(cap)

    def score(x) -> float | None:
        total = 0.0
        for p in instruments:
            v = _probe(inst, project, x, p, ledger, rng)
            if v is None:
                return None
            total += v
        _milestones(inst, project, x, ledger)
        return total

    while True:
        x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
        cur = score(x)
        if cur is None:
            return ledger
        improved = True
        while improved:
            improved = False
            best, best_x = cur, None
            for c in rng.permutation(L.N_COMPONENTS):
                for s in range(L.N_SETTINGS):
                    if s == x[c]:
                        continue
                    y = x.copy()
                    y[c] = s
                    v = score(y)
                    if v is None:
                        return ledger
                    if v > best + 2 * L.NOISE:  # a real step, not noise
                        best, best_x = v, y
            if best_x is not None:
                x, cur, improved = best_x, best, True


def setbacks(inst, project, instruments: tuple[int, ...], cap: int, rng, temperature: float = 25.0) -> Ledger:
    """Single-change search that tolerates temporary worsening (a fixed-temperature
    Metropolis walk on the summed noisy readings). One violated relation costs at least
    20 points on every instrument that sees it, so a temperature of 25 accepts a one-
    relation setback with appreciable probability and a two-relation setback rarely.
    Added for the trap calibration of September 21, 2026: the pilot labs climbed to a
    recipe whose exits all pass through a worse recipe, which plain ascent never takes."""
    ledger = Ledger(cap)

    def score(x) -> float | None:
        total = 0.0
        for p in instruments:
            v = _probe(inst, project, x, p, ledger, rng)
            if v is None:
                return None
            total += v
        _milestones(inst, project, x, ledger)
        return total

    x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
    cur = score(x)
    while cur is not None:
        y = x.copy()
        c = int(rng.integers(L.N_COMPONENTS))
        y[c] = (y[c] + 1 + int(rng.integers(L.N_SETTINGS - 1))) % L.N_SETTINGS
        v = score(y)
        if v is None:
            break
        if v >= cur or rng.random() < np.exp((v - cur) / temperature):
            x, cur = y, v
    return ledger

def _sweep(inst, project, x, k, prop, ledger, rng):
    """Probe every setting of relation k's triple on ``prop`` from base ``x``. Returns
    (best setting tuple, set of settings whose reading sits in the top band) or None
    when the budget runs out mid-sweep."""
    t = inst.triples[k]
    readings = {}
    for a in range(L.N_SETTINGS):
        for b in range(L.N_SETTINGS):
            for c in range(L.N_SETTINGS):
                y = x.copy()
                y[t[0]], y[t[1]], y[t[2]] = a, b, c
                v = _probe(inst, project, y, prop, ledger, rng)
                if v is None:
                    return None
                _milestones(inst, project, y, ledger)
                readings[(a, b, c)] = v
    top = max(readings.values())
    good = {s for s, v in readings.items() if v >= top - (L.LOSS_MIN - 2 * L.NOISE - 1)}
    best = max(readings, key=readings.get)
    return best, good


def structured(inst, project, instruments: tuple[int, ...], cap: int, rng,
               rounds: int = 2) -> tuple[Ledger, np.ndarray, dict]:
    """Block coordinate descent over the visible relations. Returns the ledger, the
    final recipe, and the learned compatible settings per relation (what this
    investigator could hand to a peer)."""
    ledger = Ledger(cap)
    x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
    learned: dict[int, set] = {}
    visible = [k for k in range(L.N_RELATIONS) if any(inst.visibility[p, k] for p in instruments)]
    for _ in range(rounds):
        for k in rng.permutation(visible):
            prop = next(p for p in instruments if inst.visibility[p, k])
            res = _sweep(inst, project, x, int(k), prop, ledger, rng)
            if res is None:
                return ledger, x, learned
            best, good = res
            learned[int(k)] = learned.get(int(k), set()) | good if int(k) in learned else good
            t = inst.triples[int(k)]
            x[t[0]], x[t[1]], x[t[2]] = best
    return ledger, x, learned


def coordinated(inst, project, cap_per_lab: int, rng, rounds: int = 3) -> dict:
    """Three single-instrument labs run ONE block coordinate descent together: each
    relation is swept by a lab that sees it, charged to that lab, from a shared base
    recipe that every lab adopts after each sweep. This is the central structured
    investigator emulated by distributed investigators exchanging their current best
    recipe and their sweep results (the pooled-models comparison of §5.1). Each lab
    stays within its own budget; success is recorded on the shared recipe."""
    shared = Ledger(3 * cap_per_lab)  # the organization's total; milestones in total units
    ledgers = [Ledger(cap_per_lab, parent=shared) for _ in range(3)]
    x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
    exhausted = False
    for _ in range(rounds):
        for k in rng.permutation(L.N_RELATIONS):
            owners = [p for p in range(3) if inst.visibility[p, int(k)]]
            prop = min(owners, key=lambda p: ledgers[p].used)  # the least-spent owner sweeps
            res = _sweep(inst, project, x, int(k), prop, ledgers[prop], rng)
            if res is None:
                exhausted = True
                break
            best, _good = res
            t = inst.triples[int(k)]
            x[t[0]], x[t[1]], x[t[2]] = best
            _milestones(inst, project, x, shared)
        if exhausted or "full_compatible" in shared.first:
            break
    return {"per_lab_used": [l.used for l in ledgers], "total_used": sum(l.used for l in ledgers),
            "first": dict(shared.first), "found_full_compatible": "full_compatible" in shared.first,
            "exhausted": exhausted}


def modular(inst, project, cap_per_lab: int, rng, rounds: int | None = 1) -> dict:
    """Three single-instrument labs, each owning one block of components (``L.BLOCKS``):
    lab p may change only its block and reads only its own instrument. Each round every
    lab sweeps all settings of its block from the current shared recipe, in parallel and
    without seeing the others' sweeps, keeps the setting its instrument reads highest,
    and the organization assembles the three blocks into the next shared recipe. One
    round is pure modular work (assembly at the end only); more rounds let the labs adjust
    to each other through the assembled recipe, still each on its own instrument.
    ``rounds=None`` repeats until a lab's budget cannot cover another sweep. Added October
    9, 2026, for the T1 benchmark of decomposable against coupled instances."""
    shared = Ledger(3 * cap_per_lab)
    ledgers = [Ledger(cap_per_lab, parent=shared) for _ in range(3)]
    x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
    sweep = L.N_SETTINGS ** 4
    done = 0
    while rounds is None or done < rounds:
        if any(ledgers[p].used + sweep > ledgers[p].cap for p in range(3)):
            break
        nxt = x.copy()
        for p in range(3):
            block = L.BLOCKS[p]
            best, best_v = None, -np.inf
            for code in range(sweep):
                y = x.copy()
                for i, c in enumerate(block):
                    y[c] = (code // L.N_SETTINGS ** i) % L.N_SETTINGS
                v = _probe(inst, project, y, p, ledgers[p], rng)
                if v > best_v:
                    best, best_v = y, v
            for c in block:
                nxt[c] = best[c]
        done += 1
        if np.array_equal(nxt, x):
            break   # no lab moves: the assembled recipe is the organization's answer
        x = nxt
        _milestones(inst, project, x, shared)
        if "full_compatible" in shared.first:
            break
    return {"per_lab_used": [l.used for l in ledgers], "total_used": sum(l.used for l in ledgers),
            "first": dict(shared.first), "found_full_compatible": "full_compatible" in shared.first,
            "rounds": done, "final_violations": int((1 - L.compat(inst, project, x)).sum())}


def task_force(inst, project, cap_per_lab: int, rng) -> dict:
    """Modular labs plus a cross-cutting task force (Thompson 5.4d; T1 design). Each round
    the labs sweep their blocks in parallel as in ``modular`` and the organization assembles
    them; then the task force sweeps, one at a time on the shared recipe, every relation
    whose triple crosses blocks, each by the lab that sees it, and keeps the best reading.
    Rounds repeat until the shared recipe is fully compatible or a lab cannot afford its
    next sweep. On a decomposable instance there is nothing for the task force to do; on a
    coupled one every relation crosses and the task force does all the integration."""
    shared = Ledger(3 * cap_per_lab)
    ledgers = [Ledger(cap_per_lab, parent=shared) for _ in range(3)]
    x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
    block_of = {c: p for p, cs in L.BLOCKS.items() for c in cs}
    crossing = [k for k, t in enumerate(inst.triples) if len({block_of[c] for c in t}) > 1]
    sweep = L.N_SETTINGS ** 4
    rounds = 0
    while True:
        if any(ledgers[p].used + sweep > ledgers[p].cap for p in range(3)):
            break
        nxt = x.copy()
        for p in range(3):
            best, best_v = None, -np.inf
            for code in range(sweep):
                y = x.copy()
                for i, c in enumerate(L.BLOCKS[p]):
                    y[c] = (code // L.N_SETTINGS ** i) % L.N_SETTINGS
                v = _probe(inst, project, y, p, ledgers[p], rng)
                if v > best_v:
                    best, best_v = y, v
            for c in L.BLOCKS[p]:
                nxt[c] = best[c]
        x = nxt
        rounds += 1
        _milestones(inst, project, x, shared)
        if "full_compatible" in shared.first:
            break
        for k in crossing:
            prop = next(p for p in range(3) if inst.visibility[p, k])
            res = _sweep(inst, project, x, k, prop, ledgers[prop], rng)
            if res is None:
                break
            t = inst.triples[k]
            x[t[0]], x[t[1]], x[t[2]] = res[0]
            _milestones(inst, project, x, shared)
        if "full_compatible" in shared.first:
            break
    return {"per_lab_used": [l.used for l in ledgers], "total_used": sum(l.used for l in ledgers),
            "first": dict(shared.first), "found_full_compatible": "full_compatible" in shared.first,
            "rounds": rounds, "final_violations": int((1 - L.compat(inst, project, x)).sum()),
            "crossing_relations": len(crossing)}


def interface_task_force(inst, project, cap_per_lab: int, rng) -> dict:
    """A task force that owns the interface and labs that own their interiors (T1 design,
    Thompson 5.4d, for the "interface" structure). The interface is every component of a
    relation that crosses blocks; a lab's interior is the rest of its block. Each round the
    task force sweeps every interface setting, each lab reading it on its own instrument, and
    keeps the setting with the highest summed reading; then the labs sweep their interiors
    in parallel with the interface held, and the organization assembles the recipe. Rounds
    repeat until the recipe is fully compatible or a lab cannot afford the next round."""
    shared = Ledger(3 * cap_per_lab)
    ledgers = [Ledger(cap_per_lab, parent=shared) for _ in range(3)]
    x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
    block_of = {c: p for p, cs in L.BLOCKS.items() for c in cs}
    interface = sorted({c for t in inst.triples if len({block_of[c] for c in t}) > 1 for c in t})
    interior = {p: [c for c in L.BLOCKS[p] if c not in interface] for p in range(3)}

    def settings(comps):
        for code in range(L.N_SETTINGS ** len(comps)):
            yield [(code // L.N_SETTINGS ** i) % L.N_SETTINGS for i in range(len(comps))]

    cost = {p: L.N_SETTINGS ** len(interface) + L.N_SETTINGS ** len(interior[p]) for p in range(3)}
    rounds = 0
    while not any(ledgers[p].used + cost[p] > ledgers[p].cap for p in range(3)):
        best, best_v = None, -np.inf
        for vals in settings(interface):
            y = x.copy()
            y[interface] = vals
            v = sum(_probe(inst, project, y, p, ledgers[p], rng) for p in range(3))
            if v > best_v:
                best, best_v = vals, v
        x[interface] = best
        nxt = x.copy()
        for p in range(3):
            pb, pv = None, -np.inf
            for vals in settings(interior[p]):
                y = x.copy()
                y[interior[p]] = vals
                v = _probe(inst, project, y, p, ledgers[p], rng)
                if v > pv:
                    pb, pv = vals, v
            nxt[interior[p]] = pb
        x = nxt
        rounds += 1
        _milestones(inst, project, x, shared)
        if "full_compatible" in shared.first:
            break
    return {"per_lab_used": [l.used for l in ledgers], "total_used": sum(l.used for l in ledgers),
            "first": dict(shared.first), "found_full_compatible": "full_compatible" in shared.first,
            "rounds": rounds, "final_violations": int((1 - L.compat(inst, project, x)).sum()),
            "interface": interface}


# ------------------------------------------------------------- table learning --
# A structured investigator that does what the block coordinate descent above does
# not: it LEARNS the visible relation tables from designed random probes by regression
# on the public diagram, then solves the constraint problem exactly and verifies.
# Unsaturated readings are additive in the violated visible relations, so with more
# probes than unknown table entries a least-squares fit recovers each table up to a
# per-relation constant, which the compatible entries pin to zero. This is the kind of
# research the proposal expects: designed interventions, a fitted model, and a table
# that another lab can use. Its single-instrument form learns only what its
# instrument sees; pooling the labs' tables is what completes the problem.

def learn_tables(inst, project, prop: int, n_probes: int, ledger: Ledger, rng,
                 threshold: float = 11.0) -> dict[int, set]:
    """Probe ``n_probes`` random recipes on instrument ``prop`` and fit the visible
    relations' tables. Returns {relation: set of compatible triple settings} for
    settings that were observed; unobserved settings are absent (unknown)."""
    visible = [k for k in range(L.N_RELATIONS) if inst.visibility[prop, k]]
    rows, ys = [], []
    for _ in range(n_probes):
        x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
        v = _probe(inst, project, x, prop, ledger, rng)
        if v is None:
            break
        _milestones(inst, project, x, ledger)
        feats = np.zeros(1 + 64 * len(visible))
        feats[0] = 1.0
        for i, k in enumerate(visible):
            feats[1 + 64 * i + int(L._triple_index(x, inst.triples[k]))] = 1.0
        rows.append(feats)
        ys.append(v)
    if len(rows) < 8:
        return {}
    A, y = np.array(rows), np.array(ys)
    theta, *_ = np.linalg.lstsq(A, y, rcond=None)
    learned: dict[int, set] = {}
    observed = A[:, 1:].sum(axis=0) > 0
    for i, k in enumerate(visible):
        coef = theta[1 + 64 * i: 1 + 64 * (i + 1)]
        seen = observed[64 * i: 64 * (i + 1)]
        if not seen.any():
            continue
        top = coef[seen].max()  # compatible settings carry the highest (zero-loss) coefficient
        good = {(s // 16, (s // 4) % 4, s % 4) for s in range(64) if seen[s] and coef[s] >= top - threshold}
        learned[k] = good
    return learned


def _csp(inst, learned: dict[int, set], rng, limit: int = 12) -> list[np.ndarray]:
    """Recipes satisfying every learned set (backtracking); unlearned relations free."""
    out: list[np.ndarray] = []
    x = np.full(L.N_COMPONENTS, -1, dtype=np.int64)
    by_comp: dict[int, list[int]] = {c: [] for c in range(L.N_COMPONENTS)}
    for k in learned:
        for c in inst.triples[k]:
            by_comp[c].append(k)

    def ok(c: int) -> bool:
        for k in by_comp[c]:
            t = inst.triples[k]
            vals = tuple(int(x[cc]) for cc in t)
            if all(v >= 0 for v in vals):
                if vals not in learned[k]:
                    return False
            elif not any(all(vals[i] < 0 or vals[i] == s[i] for i in range(3)) for s in learned[k]):
                return False
        return True

    def rec(i: int) -> None:
        if len(out) >= limit:
            return
        if i == L.N_COMPONENTS:
            out.append(x.copy())
            return
        for s in rng.permutation(L.N_SETTINGS):
            x[i] = int(s)
            if ok(i):
                rec(i + 1)
            x[i] = -1
            if len(out) >= limit:
                return

    rec(0)
    return out


def learner(inst, project, instruments: tuple[int, ...], cap: int, rng,
            n_probes: int = 450) -> tuple[Ledger, dict[int, set], int]:
    """Central table learner over the held instruments, then a constraint solve and
    verification probes on every held instrument. Returns (ledger, learned, candidates)."""
    ledger = Ledger(cap)
    learned: dict[int, set] = {}
    for p in instruments:
        for k, good in learn_tables(inst, project, p, n_probes, ledger, rng).items():
            learned[k] = learned[k] & good if k in learned else set(good)
    candidates = _csp(inst, learned, rng)
    for x in candidates:
        for p in instruments:
            if _probe(inst, project, x, p, ledger, rng) is None:
                return ledger, learned, len(candidates)
        _milestones(inst, project, x, ledger)
        if L.compat(inst, project, x).all():
            break
    return ledger, learned, len(candidates)


def pooled_learner(inst, project, cap_per_lab: int, rng, n_probes: int = 450) -> dict:
    """Three single-instrument learners within their own budgets, tables pooled, one
    constraint solve, verification probes charged to the labs whose instruments run
    them. The organization ledger reports first-touch costs in total units."""
    shared = Ledger(3 * cap_per_lab)
    ledgers = [Ledger(cap_per_lab, parent=shared) for _ in range(3)]
    learned: dict[int, set] = {}
    for p in range(3):
        for k, good in learn_tables(inst, project, p, n_probes, ledgers[p], rng).items():
            learned[k] = learned[k] & good if k in learned else set(good)
    candidates = _csp(inst, learned, rng)
    found = False
    for x in candidates:
        stop = False
        for p in range(3):
            if _probe(inst, project, x, p, ledgers[p], rng) is None:
                stop = True
                break
        _milestones(inst, project, x, shared)
        if L.compat(inst, project, x).all():
            found = True
            break
        if stop:
            break
    return {"per_lab_used": [l.used for l in ledgers], "total_used": shared.used,
            "first": dict(shared.first), "found_full_compatible": found,
            "learned_relations": len(learned), "candidates": len(candidates)}


# ------------------------------------------------- the audit's policy and sequences --

def coordinate_uniform(inst, project, cap_per_lab: int, rng, promising: float = 68.0) -> dict:
    """The policy the September 16 audit used to defeat the first benchmark: ordinary
    coordinate descent on the summed observable readings of all three instruments,
    started from the uniform recipes (all 0, all 1, ...), buying full qualification
    panels on any recipe whose three readings look promising. Each probe or panel is
    charged to the instrument's lab; success means an actual honest qualification
    (all three panel means at the target), not merely touching a compatible recipe."""
    shared = Ledger(3 * cap_per_lab)
    ledgers = [Ledger(cap_per_lab, parent=shared) for _ in range(3)]
    checked: set = set()

    def read_all(x):
        vals = []
        for p in range(3):
            v = _probe(inst, project, x, p, ledgers[p], rng)
            if v is None:
                return None
            vals.append(v)
        _milestones(inst, project, x, shared)
        return vals

    def try_qualify(x) -> bool | None:
        key = tuple(int(v) for v in x)
        if key in checked:
            return False
        checked.add(key)
        for p in range(3):
            if not ledgers[p].charge(L.N_SPECIMENS):
                return None
        panel = L.qualification_panel(inst, project, key)
        ok = bool((panel.mean(axis=1) >= L.TARGET).all())
        if ok:
            shared.mark("qualified")
        return ok

    for start in range(L.N_SETTINGS):
        x = np.full(L.N_COMPONENTS, start, dtype=np.int64)
        cur = read_all(x)
        if cur is None:
            break
        if min(cur) >= promising and try_qualify(x):
            break
        improved = True
        while improved and "qualified" not in shared.first:
            improved = False
            best, best_x, best_vals = sum(cur), None, None
            for c in rng.permutation(L.N_COMPONENTS):
                for s in range(L.N_SETTINGS):
                    if s == x[c]:
                        continue
                    y = x.copy()
                    y[c] = s
                    vals = read_all(y)
                    if vals is None:
                        return _coord_result(shared, ledgers)
                    if min(vals) >= promising:
                        q = try_qualify(y)
                        if q is None:
                            return _coord_result(shared, ledgers)
                        if q:
                            return _coord_result(shared, ledgers)
                    if sum(vals) > best + 2 * L.NOISE:
                        best, best_x, best_vals = sum(vals), y, vals
            if best_x is not None:
                x, cur, improved = best_x, best_vals, True
        if "qualified" in shared.first:
            break
    return _coord_result(shared, ledgers)


def _coord_result(shared: Ledger, ledgers: list[Ledger]) -> dict:
    return {"per_lab_used": [l.used for l in ledgers], "total_used": shared.used,
            "max_per_lab": max(l.used for l in ledgers), "first": dict(shared.first),
            "qualified": "qualified" in shared.first}


def _sample_consistent(inst, known: dict[int, set], rng, tries: int = 200) -> np.ndarray:
    """A random recipe satisfying every known compatible set (rejection, then
    backtracking as a fallback)."""
    for _ in range(tries):
        x = rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)
        if all(tuple(int(x[c]) for c in inst.triples[k]) in good for k, good in known.items()):
            return x
    cands = _csp(inst, known, rng, limit=1)
    return cands[0] if cands else rng.integers(L.N_SETTINGS, size=L.N_COMPONENTS)


def learn_tables_with_prior(inst, project, prop: int, n_probes: int, ledger: Ledger, rng,
                            known: dict[int, set], threshold: float = 11.0) -> dict[int, set]:
    """Table learning that reuses relations already known (a family's shared
    relations learned on an earlier project): probes are drawn among recipes that
    satisfy the known sets, so only the unknown visible relations contribute to the
    loss, and only their tables are fitted. Returns the newly learned sets."""
    visible = [k for k in range(L.N_RELATIONS) if inst.visibility[prop, k] and k not in known]
    if not visible:
        return {}
    rows, ys = [], []
    for _ in range(n_probes):
        x = _sample_consistent(inst, known, rng)
        v = _probe(inst, project, x, prop, ledger, rng)
        if v is None:
            break
        _milestones(inst, project, x, ledger)
        feats = np.zeros(1 + 64 * len(visible))
        feats[0] = 1.0
        for i, k in enumerate(visible):
            feats[1 + 64 * i + int(L._triple_index(x, inst.triples[k]))] = 1.0
        rows.append(feats)
        ys.append(v)
    if len(rows) < 8:
        return {}
    A, y = np.array(rows), np.array(ys)
    theta, *_ = np.linalg.lstsq(A, y, rcond=None)
    observed = A[:, 1:].sum(axis=0) > 0
    learned: dict[int, set] = {}
    for i, k in enumerate(visible):
        coef = theta[1 + 64 * i: 1 + 64 * (i + 1)]
        seen = observed[64 * i: 64 * (i + 1)]
        if seen.any():
            top = coef[seen].max()
            learned[k] = {(s // 16, (s // 4) % 4, s % 4) for s in range(64) if seen[s] and coef[s] >= top - threshold}
    return learned


def pooled_learner_sequence(inst, family: str, cap_per_lab: int, rng, n_first: int = 450,
                            n_later: int = 150) -> dict:
    """One organization of three labs works through a family's projects in order under
    ONE cumulative per-lab budget, carrying the shared relations learned on the first
    project into the next (the transfer the proposal promises). Reports, per project,
    whether a fully compatible recipe was found and confirmed by three probes, and the
    cumulative units per lab; and how many projects the organization completed."""
    shared = Ledger(3 * cap_per_lab)
    ledgers = [Ledger(cap_per_lab, parent=shared) for _ in range(3)]
    known_shared: dict[int, set] = {}
    out = {"family": family, "projects": [], "completed": 0}
    projects = [p for p in inst.projects.values() if p.family == family]
    for idx, project in enumerate(projects):
        n = n_first if idx == 0 else n_later
        learned: dict[int, set] = {}
        for p in range(3):
            new = learn_tables_with_prior(inst, project, p, n, ledgers[p], rng, known_shared)
            for k, good in new.items():
                learned[k] = learned[k] & good if k in learned else set(good)
        merged = dict(known_shared)
        for k, good in learned.items():
            merged[k] = merged[k] & good if k in merged else set(good)
        found = False
        for x in _csp(inst, merged, rng, limit=6):
            ok = True
            for p in range(3):
                if _probe(inst, project, x, p, ledgers[p], rng) is None:
                    ok = False
                    break
            if not ok:
                break
            if L.compat(inst, project, x).all():
                found = True
                break
        out["projects"].append({"project": project.project_id, "type": project.ptype, "found": found,
                                "units_per_lab": [l.used for l in ledgers], "learned_new": sorted(learned)})
        if found:
            out["completed"] += 1
            for k in range(L.N_SHARED):  # shared relations carry to the family's next project
                if k in merged:
                    known_shared[k] = merged[k]
        if any(l.used >= cap_per_lab for l in ledgers):
            break
    out["units_per_lab"] = [l.used for l in ledgers]
    return out
