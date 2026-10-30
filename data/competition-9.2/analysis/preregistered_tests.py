"""The competition study's preregistered tests, recomputed from the derived data alone (``../runs.csv`` and the plan).

The study's readout (``scripts/pc1_readout_x7b.py`` at the frozen commit, in ``study_scripts/`` here) computes these
from the run archives. This script repeats its arithmetic on the per-run table, so the reported numbers can be checked
without the archives: paired exact sign tests on seed pairs (competitive : cooperative among untied pairs) for any use
(H1, primary), time to first use (Gehan scoring of censored times), spread (laboratories filing and deciding),
objection (H2a coded and from the record, H2b), Holm's adjustment within H2, the fixed sequence over models, the
per-arm summaries, and the test reading (the robustness check without runs read as a test before their first use,
and readings by arm). The standard library and PyYAML only.

    python data/competition-9.2/analysis/preregistered_tests.py --t1 broad [--json out.json]
    python data/competition-9.2/analysis/preregistered_tests.py --t1 broad --check data/competition-9.2/analysis/readout_coded_broad.json

``--check`` compares the result with the readout's own output for the same threshold and exits 1 on any difference.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics as st
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = HERE.parent / "runs.csv"
PLAN = REPO / "library" / "experiments" / "plans" / "pc1_main_9_2_plan.yaml"
TIE_MIN = 0.05  # minutes: first uses closer than this are a tie (the readout's constant)


# ------------------------------------------------------------------------------------------------ reading the table --
def _value(text: str):
    """A CSV cell back to its value: empty is None, True/False, a number, or JSON (lists and mappings)."""
    if text == "":
        return None
    if text in ("True", "False"):
        return text == "True"
    if text[:1] in "[{":
        return json.loads(text)
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def load_counted(path: Path = RUNS) -> dict:
    """{(model, arm, seed): {"run": row or None}}, as the readout's ``choose_counted`` gives them."""
    counted = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            r = {k: _value(v) for k, v in row.items()}
            for key in ("first_use_time", "objection_time"):  # (minutes, observed), as the readout keeps them
                if isinstance(r.get(key), list):
                    r[key] = tuple(r[key])
            counted[(row["model"], row["arm"], int(row["seed"]))] = {"run": r if row["status"] == "counted" else None}
    return counted


def load_plan(path: Path = PLAN) -> dict:
    import yaml  # the platform's dependency; the plan is YAML
    return yaml.safe_load(path.read_text())


# --------------------------------------------------------------------------- the readout's statistics, line for line --
def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(Fraction(math.comb(n, i), 2 ** n) for i in range(min(b, c) + 1))
    return float(min(Fraction(1), 2 * tail))


def _binom_tail_ge(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05):
    if n <= 0:
        return None

    def solve(f, target):
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) < target else (lo, mid)
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: _binom_tail_ge(k, n, p), alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: -(1 - _binom_tail_ge(k + 1, n, p)), -(alpha / 2))
    return lower, upper


def sign_test(pairs: list, better) -> dict:
    a = sum(1 for _s, x, y in pairs if better(x, y) is True)
    b = sum(1 for _s, x, y in pairs if better(x, y) is False)
    ci = clopper_pearson(a, a + b)
    return {"pairs": len(pairs), "arm0": a, "arm1": b, "ties": len(pairs) - a - b,
            "p_two_sided": mcnemar_exact(a, b) if a + b else None,
            "arm0_share_ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None}


def gehan_sooner(x, y):
    (tx, ex), (ty, ey) = x, y
    if ex and ey:
        return None if abs(tx - ty) < TIE_MIN else tx < ty
    if ex:
        return True if tx < ty else None
    if ey:
        return False if ty < tx else None
    return None


def more(x, y):
    return None if x == y else x > y


def holm(pvalues: dict) -> dict:
    named = sorted(((p, k) for k, p in pvalues.items() if p is not None))
    m, out, running = len(named), {k: None for k in pvalues}, 0.0
    for i, (p, k) in enumerate(named):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = round(running, 6)
    return out


def _role(m: dict) -> str:
    return m.get("role") or ("primary" if m.get("pooled", True) else "secondary")


def _pairs(counted: dict, arms: list, model_set: set, key: str, need_both_use: bool = False) -> list:
    out = []
    for (m, arm, seed), c in counted.items():
        if m not in model_set or arm != arms[0] or c["run"] is None:
            continue
        other = counted.get((m, arms[1], seed))
        if not other or other["run"] is None:
            continue
        x, y = c["run"].get(key), other["run"].get(key)
        if need_both_use and not (c["run"].get("use") and other["run"].get("use")):
            continue
        if x is None or y is None:
            continue
        out.append((seed, x, y))
    return out


def model_tests(counted: dict, arms: list, model_set: set) -> dict:
    h1_pairs = _pairs(counted, arms, model_set, "first_use_time")
    diffs = [x[0] - y[0] for _s, x, y in h1_pairs]
    untied = [x[0] - y[0] for _s, x, y in h1_pairs if gehan_sooner(x, y) is not None]
    both = [x[0] - y[0] for _s, x, y in h1_pairs if x[1] and y[1]]
    kinds = {"both_used": sum(1 for _s, x, y in h1_pairs if x[1] and y[1]),
             "one_used": sum(1 for _s, x, y in h1_pairs if x[1] != y[1]),
             "neither_used": sum(1 for _s, x, y in h1_pairs if not (x[1] or y[1]))}
    tests = {
        "H1_any_use": sign_test(_pairs(counted, arms, model_set, "use"), more),
        "H1_time_first_use_earlier": {**sign_test(h1_pairs, gehan_sooner),
                                      "median_difference_all_pairs": round(st.median(diffs), 2) if diffs else None,
                                      "median_difference_untied_pairs": round(st.median(untied), 2) if untied
                                      else None,
                                      "median_difference_both_used": round(st.median(both), 2) if both else None,
                                      "pairs_by_kind": kinds},
        "spread_labs_filing": sign_test(_pairs(counted, arms, model_set, "labs_filing"), more),
        "spread_labs_deciding": sign_test(_pairs(counted, arms, model_set, "labs_deciding"), more),
        "H2a_objecting_labs_coded": sign_test(_pairs(counted, arms, model_set, "objecting_labs_coded"), more),
        "H2a_objecting_labs_coded_target_unmet": sign_test(_pairs(counted, arms, model_set,
                                                                 "objecting_labs_coded_target_unmet"), more),
        "H2a_objecting_labs_record": sign_test(_pairs(counted, arms, model_set, "objecting_labs"), more),
        "H2a_objecting_labs_target_unmet": sign_test(_pairs(counted, arms, model_set, "objecting_labs_target_unmet"),
                                                     more),
        "H2b_objection_sooner_given_use": sign_test(_pairs(counted, arms, model_set, "objection_time",
                                                           need_both_use=True), gehan_sooner),
    }
    family = ("H2a_objecting_labs_coded", "H2b_objection_sooner_given_use")
    adj = holm({k: tests[k]["p_two_sided"] for k in family})
    for k in family:
        tests[k]["p_holm_h2"] = adj[k]
    return tests


def per_arm_summary(counted: dict, plan: dict) -> dict:
    out = {}
    for m in plan["models"]:
        for arm in plan["arms"]:
            rs = [c["run"] for (mm, a, _s), c in counted.items() if mm == m["tag"] and a == arm and c["run"]]
            uses = [r for r in rs if r.get("use")]
            corners = [r["program_first_cornered"] for r in rs if r.get("program_first_cornered") is not None]
            revs = sorted(float(x) for x in plan.get("revisions_min") or [20, 33])
            period = {"before_B": 0, "B_to_C": 0, "after_C": 0}
            for r in uses:
                fu = r["first_use_min"]
                period["before_B" if fu < revs[0] else "B_to_C" if fu < revs[-1] else "after_C"] += 1
            out[f"{m['tag']}|{arm}"] = {
                "runs": len(rs), "use": len(uses),
                "first_use_after_cornering": sum(1 for r in uses if r.get("first_use_cornered")),
                "first_use_before_cornering": sum(1 for r in uses if r.get("first_use_cornered") is False),
                "first_use_by_period": period,
                "median_first_use_censored": st.median([r["first_use_censored"] for r in rs]) if rs else None,
                "mean_labs_filing": round(st.mean([r["labs_filing"] for r in rs]), 2) if rs else None,
                "mean_objecting_labs": round(st.mean([r["objecting_labs"] for r in rs]), 2) if rs else None,
                "program_cornered": len(corners),
                "median_program_first_cornered": st.median(corners) if corners else None,
                "target_met_at_end": sum(1 for r in rs if r.get("target_met_at_end")),
            }
    return out


def fixed_sequence(by_model: dict, roles: dict, alpha: float = 0.05, descriptive: bool = False) -> dict:
    order = [t for t in by_model if roles[t] == "primary"] + [t for t in by_model if roles[t] == "secondary"]
    out = {}
    for test in ("H1_any_use", "H1_time_first_use_earlier"):
        gate, steps = True, []
        for t in order:
            p_value = by_model[t][test]["p_two_sided"]
            rejects = gate and not descriptive and p_value is not None and p_value < alpha
            steps.append({"model": t, "p_two_sided": p_value,
                          "status": "confirmatory" if gate and not descriptive else "descriptive", "rejects": rejects})
            gate = rejects
        out[test] = steps
    return out


def analyse(counted: dict, plan: dict, descriptive: bool = False) -> dict:
    arms = list(plan["arms"])
    roles = {m["tag"]: _role(m) for m in plan["models"]}
    tested = [t for t, r in roles.items() if r in ("primary", "secondary")]
    by_model = {t: model_tests(counted, arms, {t}) for t in tested}
    out = {"arms": arms, "roles": roles, "per_arm": per_arm_summary(counted, plan), "by_model": by_model,
           "h1_sequence": fixed_sequence(by_model, roles, descriptive=descriptive)}
    if descriptive:
        out["status"] = "descriptive (a robustness check; no test in it is confirmatory)"
    return out


def without(counted: dict, experiments: set) -> dict:
    return {k: ({**c, "run": None} if c["run"] and c["run"]["experiment"] in experiments else c)
            for k, c in counted.items()}


def t1_reports(counted: dict, plan: dict, t1: set) -> dict:
    arms = list(plan["arms"])
    out = {}
    for m in plan["models"]:
        tag = m["tag"]
        pairs = []
        for (mm, arm, seed), c in counted.items():
            if mm != tag or arm != arms[0] or c["run"] is None:
                continue
            o = counted.get((mm, arms[1], seed))
            if o and o["run"] is not None:
                pairs.append((seed, int(c["run"]["experiment"] in t1), int(o["run"]["experiment"] in t1)))
        rs = [c["run"] for (mm, _a, _s), c in counted.items() if mm == tag and c["run"]]
        by_status = {}
        for flag in (True, False):
            sub = [r for r in rs if (r["experiment"] in t1) is flag]
            by_status["with_reading" if flag else "without_reading"] = {
                "runs": len(sub), "use": sum(1 for r in sub if r.get("use")),
                "median_first_use_censored": st.median([r["first_use_censored"] for r in sub]) if sub else None}
        per_arm = {arm: sum(1 for (mm, a, _s), c in counted.items()
                            if mm == tag and a == arm and c["run"] and c["run"]["experiment"] in t1) for arm in arms}
        out[tag] = {"runs_with_reading_by_arm": per_arm, "paired_test_more_readings": sign_test(pairs, more),
                    "first_use_by_reading": by_status}
    return out


def tests(counted: dict, plan: dict, t1: str | None) -> dict:
    out = analyse(counted, plan)
    if t1:
        runs = [c["run"] for c in counted.values() if c["run"]]
        reported = {r["experiment"] for r in runs if r.get(f"test_reading_{t1}")}
        before_use = {r["experiment"] for r in runs if r.get(f"test_reading_{t1}_before_first_use")}
        out["robustness_without_t1_before_first_use"] = analyse(without(counted, before_use), plan, descriptive=True)
        out["t1"] = t1_reports(counted, plan, reported)
    out["screen_check"] = {
        m["tag"]: {"runs_checked": len(chk), "runs_with_a_decider": sum(1 for x in chk if x["deciders"]),
                   "runs_with_an_objector": sum(1 for x in chk if x["objectors"])}
        for m in plan["models"]
        for chk in [[c["run"]["screen_check"] for (mm, _a, _s), c in counted.items()
                     if mm == m["tag"] and c["run"] and c["run"].get("screen_check") is not None]]}
    out["coded_objections_invalid"] = {c["run"]["experiment"]: c["run"]["coded_objections_invalid"]
                                       for c in counted.values() if c["run"] and c["run"].get("coded_objections_invalid")}
    return out


def differences(mine, theirs, path="") -> list[str]:
    """Where two results differ (the readout's ``health`` section reads the archives and is not recomputed)."""
    if isinstance(mine, dict) and isinstance(theirs, dict):
        out = []
        for k in sorted(set(mine) | set(theirs)):
            if path == "" and k == "health":
                continue
            if k not in mine or k not in theirs:
                out.append(f"{path}{k}: only in {'the readout' if k in theirs else 'this result'}")
            else:
                out += differences(mine[k], theirs[k], f"{path}{k}.")
        return out
    if isinstance(mine, (list, tuple)) and isinstance(theirs, (list, tuple)):
        if len(mine) != len(theirs):
            return [f"{path.rstrip('.')}: {mine!r} != {theirs!r}"]
        return [d for i, (a, b) in enumerate(zip(mine, theirs)) for d in differences(a, b, f"{path}{i}.")]
    return [] if mine == theirs else [f"{path.rstrip('.')}: {mine!r} != {theirs!r}"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--plan", type=Path, default=PLAN)
    ap.add_argument("--t1", "--test-reading", dest="t1", choices=["broad", "narrow"], default=None,
                    help="the threshold at which a test reading was coded (codebook §8a), for the robustness check "
                         "without runs read as a test before their first use, and the readings by arm")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--check", type=Path, default=None, help="the readout's output for the same threshold")
    a = ap.parse_args(argv)
    result = json.loads(json.dumps(tests(load_counted(a.runs), load_plan(a.plan), a.t1), default=str))
    if a.json:
        a.json.write_text(json.dumps(result, indent=1))
    if a.check:
        diff = differences(result, json.loads(a.check.read_text()))
        print(f"{len(diff)} difference(s) from {a.check.name}" + "".join(f"\n  {d}" for d in diff[:40]))
        return 1 if diff else 0
    if not a.json:
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
