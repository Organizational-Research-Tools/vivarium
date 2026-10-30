"""Agreement between the two coders of PC1 9.2 (preregistration §5; pc1_process_coding.md §7.4): share and Cohen's kappa
over laboratories, per studied model, for decided or not (E is F or I), licence citation (F is SL), a valid coded
objection (``coded_objections``) and the path class computed with the record's cornering (P1, P1d, P2 to P5). Lists the
disagreements for the PI's adjudication. Reads the two coding files and the runs; no model calls.

    PYTHONPATH="$PWD" python scripts/pc1_coding_agreement.py first.json second.json screen.json [--json out.json]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from oaos2.tasks.plugins.materials_lab.derived import cornered_at, cornering, run_clock, run_minute
from scripts.pc1_readout_x7b import _events, coded_objections

MODELS = ("glm53", "gpt6luna", "sonnet46")


def kappa(pairs: list[tuple]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    cats = {x for p in pairs for x in p}
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def run_context(run_dir: Path) -> dict:
    report = json.loads((run_dir / "derived" / "materials_lab_report.json").read_text())
    reports = sorted(({**r, "minute_exact": float(r["minute_exact"] if r.get("minute_exact") is not None
                                                  else r["minute"])}
                      for r in (report.get("restricted_use") or {}).get("reports") or [] if r.get("in_work_period")),
                     key=lambda r: r["minute_exact"])
    events = _events(run_dir)
    clock = run_clock(events)
    end = (clock or {}).get("observation_minute") or 50.0
    return {"events": events, "reports": reports, "end": float(end), "corner": cornering(events, run_dir),
            "minute": {e.get("sequence_number"): run_minute(events, e.get("timestamp"), clock=clock) for e in events}}


def lab_fields(lab: str, v: dict, ctx: dict) -> dict:
    e = v.get("E") or {}
    code = str(e.get("code") or "").strip()[:1]
    decided = code in ("F", "I")
    licence = (v.get("F") or {}).get("form") == "SL"
    objection = bool(coded_objections({lab: v}, ctx["events"], ctx["reports"], ctx["end"])[0])
    if decided:
        minute = ctx["minute"].get(e.get("seq"))
        cornered = cornered_at(ctx["corner"], lab, minute) if minute is not None else None
        path = ("P3" if licence else "P2") if cornered else ("P5" if licence else "P4")
    else:
        path = "P1" if (ctx["corner"]["labs"].get(lab) or {}).get("first_cornered") is not None else "P1d"
    return {"decided": decided, "licence": licence, "objection": objection, "path": path, "E": code or "?"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("first")
    ap.add_argument("second")
    ap.add_argument("screen")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    first, second = json.loads(Path(a.first).read_text()), json.loads(Path(a.second).read_text())
    dirs = {Path(r["run"]).parent.parent.name: Path(r["run"]) for r in json.loads(Path(a.screen).read_text())}
    pairs, disagreements, skipped = defaultdict(lambda: defaultdict(list)), [], []
    for name in sorted(second):
        model = next((m for m in MODELS if f"_{m}_" in name), "?")
        l1, l2 = (first.get(name) or {}).get("labs") or {}, (second.get(name) or {}).get("labs") or {}
        ctx = run_context(dirs[name])
        for lab in sorted(set(l1) | set(l2)):
            if lab not in l1 or lab not in l2:
                skipped.append(f"{name}:{lab}")
                continue
            f1, f2 = lab_fields(lab, l1[lab], ctx), lab_fields(lab, l2[lab], ctx)
            for k in ("decided", "licence", "objection", "path"):
                pairs[model][k].append((f1[k], f2[k]))
                pairs["all"][k].append((f1[k], f2[k]))
            diff = [k for k in ("decided", "licence", "objection", "path") if f1[k] != f2[k]]
            if diff:
                disagreements.append({"run": name, "lab": lab, "fields": diff, "first": f1, "second": f2})
    out = {"agreement": {m: {k: {"labs": len(p), "share": round(sum(x == y for x, y in p) / len(p), 3) if p else None,
                                 "kappa": kappa(p)} for k, p in fields.items()} for m, fields in pairs.items()},
           "not_compared": skipped, "disagreements": disagreements}
    text = json.dumps(out, indent=1, default=str)
    if a.json:
        Path(a.json).write_text(text)
    print(json.dumps(out["agreement"], indent=1))
    print(f"{len(disagreements)} laboratories disagree on some field; {len(skipped)} not coded by both")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
