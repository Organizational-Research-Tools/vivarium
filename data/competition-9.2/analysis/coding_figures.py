"""The coder agreement and the exploratory tables of the results page, recomputed from the released coding sheets.

Reads ``../coding/`` and ``../runs.csv``; no run archive and no model call. Decided and licence citation are recomputed
from the two coding sheets. Objection and the path class also need the run's events, so
``../coding/agreement_inputs.csv`` gives each laboratory's values as ``scripts/pc1_coding_agreement.py`` computed them
from the archives; the agreement on those two is recomputed from that table, and the table's decided and licence
columns are compared with the sheets. ``coding_figures.json`` holds the figures as the results page reports them,
typed from the page, each to the page's own rounding; ``--check`` compares this script's result with them, and with
``../coding/agreement.json`` exactly.

    python data/competition-9.2/analysis/coding_figures.py [--json out.json]
    python data/competition-9.2/analysis/coding_figures.py --check data/competition-9.2/analysis/coding_figures.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import preregistered_tests as T  # noqa: E402

CODING = HERE.parent / "coding"
MODELS = ("glm53", "gpt6luna", "sonnet46")
FIELDS = ("decided", "licence", "objection", "path")
ARMS = ("competitive", "cooperative")


def kappa(pairs: list[tuple]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    cats = {x for p in pairs for x in p}
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def _read(path: Path):
    return json.loads(path.read_text())


def agreement(coding: Path) -> dict:
    pairs: dict = defaultdict(lambda: defaultdict(list))
    with (coding / "agreement_inputs.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            model = next((m for m in MODELS if f"_{m}_" in row["experiment"]), "?")
            for group in (model, "all"):
                pairs[group][row["field"]].append((row["first"], row["second"]))
    return {group: {k: {"labs": len(p), "share": round(sum(x == y for x, y in p) / len(p), 3), "kappa": kappa(p)}
                    for k, p in fields.items()} for group, fields in pairs.items()}


def sheets_against_inputs(coding: Path) -> int:
    """Laboratories whose decided or licence value in the inputs table differs from the coding sheets."""
    first, second = _read(coding / "first_coding.json"), _read(coding / "second_coding.json")

    def value(sheet: dict, name: str, lab: str, field: str) -> bool:
        c = sheet[name]["labs"][lab]
        if field == "decided":
            return str((c.get("E") or {}).get("code") or "").strip()[:1] in ("F", "I")
        return (c.get("F") or {}).get("form") == "SL"

    differ = 0
    with (coding / "agreement_inputs.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["field"] in ("decided", "licence"):
                differ += (str(value(first, row["experiment"], row["lab"], row["field"])) != row["first"]
                           or str(value(second, row["experiment"], row["lab"], row["field"])) != row["second"])
    return differ


def reading(coding: Path, folder: str, first: str, second: str) -> dict:
    key = _read(coding / folder / f"{folder}_key.json")
    one, two = (_read(coding / folder / f) for f in (first, second))
    code = lambda v: v["code"] if isinstance(v, dict) else v  # noqa: E731
    pairs = [(code(one[i]), code(two[i])) for i in key]
    table = {arm: {"passages": sum(key[i].get("arm") == arm for i in key),
                   "first": dict(sorted(Counter(code(one[i]) for i in key if key[i].get("arm") == arm).items())),
                   "second": dict(sorted(Counter(code(two[i]) for i in key if key[i].get("arm") == arm).items()))}
             for arm in ARMS}
    return {"passages": len(pairs), "agree": sum(a == b for a, b in pairs), "kappa": round(kappa(pairs), 2), "by_arm": table}


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]]: tables no more probable than the observed one."""
    row, col, n = a + b, a + c, a + b + c + d
    prob = lambda x: math.comb(col, x) * math.comb(n - col, row - x) / math.comb(n, row)  # noqa: E731
    seen = prob(a)
    return sum(p for x in range(max(0, row + col - n), min(row, col) + 1) if (p := prob(x)) <= seen * (1 + 1e-9))


def wilcoxon_two_sided(differences: list[float]) -> float:
    """The signed-rank test, zeros dropped, ties averaged, normal approximation with the tie correction."""
    d = sorted((abs(x), x > 0) for x in differences if x)
    n = len(d)
    if not n:
        return 1.0
    ranks: list[float] = []
    i, ties = 0, 0.0
    while i < n:
        j = i
        while j + 1 < n and d[j + 1][0] == d[i][0]:
            j += 1
        ranks += [(i + j) / 2 + 1] * (j - i + 1)
        ties += (j - i + 1) ** 3 - (j - i + 1)
        i = j + 1
    w = sum(r for r, (_, positive) in zip(ranks, d) if positive)
    mean, var = n * (n + 1) / 4, n * (n + 1) * (2 * n + 1) / 24 - ties / 48
    return math.erfc(abs(w - mean) / math.sqrt(var) / math.sqrt(2))


def filings_and_objection(counted: dict) -> dict:
    out = {}
    for tag in MODELS[:2]:
        runs = {a: {s: c["run"] for (m, aa, s), c in counted.items() if m == tag and aa == a and c["run"]} for a in ARMS}
        filings = {a: sum(r.get("n_restricted_reports") or 0 for r in runs[a].values()) for a in ARMS}
        seeds = set(runs[ARMS[0]]) & set(runs[ARMS[1]])
        diffs = [(runs[ARMS[0]][s].get("n_restricted_reports") or 0) - (runs[ARMS[1]][s].get("n_restricted_reports") or 0)
                 for s in seeds]
        used = {a: [r for r in runs[a].values() if r.get("use")] for a in ARMS}
        objected = {a: [r for r in used[a] if (r.get("objecting_labs_coded") or 0) > 0] for a in ARMS}
        after = {a: [r["objection_time"][0] for r in objected[a] if isinstance(r.get("objection_time"), tuple)] for a in ARMS}
        out[tag] = {
            "filings": filings, "filings_wilcoxon_p": round(wilcoxon_two_sided(diffs), 2),
            "runs_with_use": {a: len(used[a]) for a in ARMS}, "runs_with_objection": {a: len(objected[a]) for a in ARMS},
            "objection_fisher_p": round(fisher_two_sided(len(objected[ARMS[0]]), len(used[ARMS[0]]) - len(objected[ARMS[0]]),
                                                         len(objected[ARMS[1]]), len(used[ARMS[1]]) - len(objected[ARMS[1]])), 2),
            "objecting_labs_per_run_with_use": {a: round(sum(r.get("objecting_labs_coded") or 0 for r in used[a]) / len(used[a]), 2)
                                                for a in ARMS},
            "median_minutes_to_first_objection": {a: round(statistics.median(after[a]), 1) if after[a] else None for a in ARMS}}
    return out


def test_reading(coding: Path, counted: dict) -> dict:
    frozen = {n: _read(coding / "test_reading" / f"t1_frozen_{n}.json") for n in ("broad", "narrow")}
    out = {}
    for name, lists in frozen.items():
        out[name] = {"frozen_list_by_model": {m: sum(f"_{m}_" in run for run in lists) for m in MODELS},
                     "table_by_model": {m: sum(1 for (mm, _a, _s), c in counted.items() if mm == m and c["run"]
                                               and c["run"].get(f"test_reading_{name}")) for m in MODELS}}
    return out


def rounded_equal(value, page) -> bool:
    decimals = len(repr(page).partition(".")[2]) if isinstance(page, float) else 0
    return value is not None and round(value, decimals) == page


def against_page(result, page, path: str = "") -> list[str]:
    """Differences between the result and every figure the page gives, at the page's rounding."""
    if isinstance(page, dict):
        return [d for k, v in page.items() for d in against_page((result or {}).get(k), v, f"{path}.{k}")]
    if isinstance(page, list):
        return [d for i, v in enumerate(page) for d in against_page(result[i], v, f"{path}[{i}]")]
    if isinstance(page, (int, float)) and not isinstance(page, bool):
        return [] if rounded_equal(result, page) else [f"{path}: {result} against {page}"]
    return [] if result == page else [f"{path}: {result} against {page}"]


def page_form(result: dict) -> dict:
    """The agreement table as the page sets it out: decided, objection, licence, path."""
    order = ("decided", "objection", "licence", "path")
    return {**result, "agreement": {m: {"labs": result["agreement"][m]["decided"]["labs"],
                                        "share": [result["agreement"][m][k]["share"] for k in order],
                                        "kappa": [result["agreement"][m][k]["kappa"] for k in order]}
                                    for m in MODELS}}


def figures(coding: Path, counted: dict) -> dict:
    return {"agreement": agreement(coding), "inputs_differing_from_sheets": sheets_against_inputs(coding),
            "warrants": reading(coding, "licence", "licence_codes.json", "licence_codes_second.json"),
            "objection_reasons": reading(coding, "objection", "objection_codes.json", "objection_codes_second.json"),
            "motives": reading(coding, "motive", "motive_codes_gpt-6.1-terra.json", "motive_codes_claude-haiku-4-5.json"),
            "filings_and_objection": filings_and_objection(counted), "test_reading": test_reading(coding, counted)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--coding", type=Path, default=CODING)
    ap.add_argument("--runs", type=Path, default=T.RUNS)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--check", type=Path, default=None, help="the figures as the results page reports them")
    a = ap.parse_args(argv)
    result = json.loads(json.dumps(figures(a.coding, T.load_counted(a.runs))))
    if a.json:
        a.json.write_text(json.dumps(result, indent=1))
    if a.check:
        diff = against_page(page_form(result), json.loads(a.check.read_text()))
        diff += T.differences(result["agreement"], _read(a.coding / "agreement.json")["agreement"], "agreement.json")
        print(f"{len(diff)} difference(s) from {a.check.name} and agreement.json" + "".join(f"\n  {d}" for d in diff[:40]))
        return 1 if diff else 0
    if not a.json:
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
