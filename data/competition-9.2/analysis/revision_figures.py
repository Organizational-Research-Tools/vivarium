"""The figures the results page's revision of October 29, 2026 added, recomputed from the derived data alone.

The revision reports, beside the preregistered tests that ``preregistered_tests.py`` repeats: knowing use (the first
user coded as having decided to use, E = F, without the ``unknowing`` mark; preregistration §4) and accepted
restricted filings, each by arm with the paired sign test; and the test-reading check on the pinned screen's hits
alone, the preregistered covariate that the study's deviation of October 22 kept the analyses on (readings by arm and
H1 without the runs read as a test before their first use). They were first computed from the run archives;
``revision_figures.json`` holds that computation, and ``--check`` compares this script's result with it.

    python data/competition-9.2/analysis/revision_figures.py [--json out.json]
    python data/competition-9.2/analysis/revision_figures.py --check data/competition-9.2/analysis/revision_figures.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import preregistered_tests as T  # noqa: E402


def figures(counted: dict, plan: dict) -> dict:
    arms = list(plan["arms"])
    tags = [m["tag"] for m in plan["models"]]
    out = {}
    for tag in tags:
        out[tag] = {}
        for key in ("knowing_use", "accepted"):
            per_arm = {a: sum(1 for (m, aa, _s), c in counted.items() if m == tag and aa == a and c["run"]
                              and c["run"].get(key)) for a in arms}
            out[tag][key] = {"per_arm": per_arm, "test": T.sign_test(T._pairs(counted, arms, {tag}, key), T.more)}
    for name in ("broad_pinned", "narrow_pinned"):
        result = T.tests(counted, plan, name)
        out[name] = {
            "runs_with_reading": {tag: sum(1 for (m, _a, _s), c in counted.items() if m == tag and c["run"]
                                           and c["run"].get(f"test_reading_{name}")) for tag in tags},
            "rate_by_arm": result["t1"],
            "robustness_H1": {t: result["robustness_without_t1_before_first_use"]["by_model"][t]["H1_any_use"]
                              for t in result["robustness_without_t1_before_first_use"]["by_model"]}}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", type=Path, default=T.RUNS)
    ap.add_argument("--plan", type=Path, default=T.PLAN)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--check", type=Path, default=None, help="the figures as computed from the archives")
    a = ap.parse_args(argv)
    result = json.loads(json.dumps(figures(T.load_counted(a.runs), T.load_plan(a.plan)), default=str))
    if a.json:
        a.json.write_text(json.dumps(result, indent=1))
    if a.check:
        diff = T.differences(result, json.loads(a.check.read_text()))
        print(f"{len(diff)} difference(s) from {a.check.name}" + "".join(f"\n  {d}" for d in diff[:40]))
        return 1 if diff else 0
    if not a.json:
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
