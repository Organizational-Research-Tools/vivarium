"""One paid run of the materials workshop on a named preset (the competition study's competitive arm by default).

This script spends model money. It refuses to run without ``--go``; with ``--go`` the run is billed to your
provider key. It launches a single
organization on preset ``competition_competitive`` with a hard spending cap and prints the
archive path; read the run with ``scripts/materials_lab_report.py`` afterwards.

Run from the repository root:
  PYTHONPATH="$PWD" python scripts/run_materials_lab_smoke.py --model openrouter/z-ai/glm-5.3-flash@z-ai --reasoning-budget 1000 --seed 41 --cap 15 [--go]
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
from pathlib import Path

from oaos2.experiments.runner import run_org_live
from oaos2.experiments.stop import RunStop, install_signal_stop
from oaos2.organizations.loader import load_org_spec
from oaos2.tasks.plugins.materials_lab.vocabulary import pack_for

RUNS = Path("runs")
CONTAINER_MARGIN_S = 900  # the agents' containers must outlive participation, drain, and assessment


def wall_clock_for(org) -> int:
    """The agents' container lifetime for an organization: its participant deadline plus
    the pool's drain and assessment bounds plus a margin. The runner's default of 1,800 s
    silently ended every container at 30 minutes of a 45-minute run on September 17, 2026,
    after which the compute tool returned "container is not running" while the model
    kept working; the reviewer of that day found it in the launch records."""
    b = dict((org.live_coordination or {}).get("bounds") or {})
    return int(float(b.get("participant_deadline_s", 600)) + float(b.get("observation_s", 0))
               + float(b.get("drain_s", 5)) + float(b.get("assessment_s", 5)) + CONTAINER_MARGIN_S)


def observed_spend_per_lab_minute(model_ref: str, runs_root: Path) -> tuple[float, int] | None:
    """The highest spend per laboratory-minute among finished materials-lab runs of ``model_ref`` under ``runs_root``
    (cost over laboratories times the minutes until the last response), and how many runs were read; None if none."""
    import json
    rates = []
    for status in runs_root.glob("*/*/materials_lab/*/run_status.json"):
        try:
            st = json.loads(status.read_text())
        except (OSError, ValueError):
            continue
        if st.get("model_ref") != model_ref or not st.get("cost_usd") or not st.get("closed"):
            continue
        t0 = last = None
        labs = set()
        events = status.parent / "trace" / "events.jsonl"
        if not events.exists():
            continue
        for line in events.open():
            if '"run.started"' in line or '"model.responded"' in line:
                e = json.loads(line)
                if e["event_class"] == "run.started":
                    t0 = e["timestamp"]
                elif e.get("agent_id"):
                    last = e["timestamp"]
                    labs.add(e["agent_id"])
        if t0 is None or last is None or last - t0 < 300 or not labs:
            continue
        rates.append(float(st["cost_usd"]) / (len(labs) * (last - t0) / 60))
    return (max(rates), len(rates)) if rates else None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true", help="actually launch (paid)")
    ap.add_argument("--seed", type=int, default=4, help="instance seed")
    ap.add_argument("--cap", type=float, default=15.0, help="hard USD ceiling for the run")
    ap.add_argument("--calls", type=int, default=40, help="model calls per lab")
    ap.add_argument("--model", default="anthropic/claude-sonnet-4-6")
    ap.add_argument("--effort", default=None,
                    help="reasoning effort for a model set by an effort level (Claude Sonnet 5.5): low, medium or high; "
                         "a study setting, required for such a model and refused for the others")
    ap.add_argument("--reasoning-budget", type=int, default=8000,
                    help="reasoning budget in tokens for a budget model (October 12, 2026); OpenAI-style models map it to "
                         "an effort (2,048 or less: low; 16,384 or more: high). Default 8,000, as in every earlier run")
    ap.add_argument("--guard-rate", type=float, default=None,
                    help="the cap guard's spend per lab-minute in USD, fixed for a study, instead of the rate observed "
                         "in earlier runs, which rises as runs accumulate (ported from the competition study's "
                         "launcher, October 29, 2026)")
    ap.add_argument("--max-output", type=int, default=20000,
                    help="per-call output token ceiling (thinking included); the platform default of "
                         "12288 ended the first control run inside its thinking")
    ap.add_argument("--pressure", type=float, default=0.9,
                    help="share of the cap at which the budget notice fires; the platform default of "
                         "0.7 ended the September 18 control with a quarter of its budget unspent")
    ap.add_argument("--context-budget", type=int, default=None,
                    help="per-lab context budget in estimator tokens; default = the preset's "
                         "context_budget_tokens (60000)")
    ap.add_argument("--no-objective", action="store_true",
                    help="calibration only: run without the preset's assigned-objective sentence")
    ap.add_argument("--preset", default="competition_competitive",
                    help="the organization preset (default: the competition study's competitive arm)")
    ap.add_argument("--experiment", default=None, help="experiment id; default <preset>_s<seed>")
    ap.add_argument("--series", default="live",
                    help="folder under runs/ that holds this study's runs, so they read as one lineage")
    ap.add_argument("--allow-tight-cap", action="store_true",
                    help="launch even if the cap is below the guard's minimum (the cap may then retire labs mid-run)")
    ap.add_argument("--minutes", type=float, default=None,
                    help="participant deadline in minutes, overriding the preset's (a shortened shakedown); the "
                         "reminders and any notice keep their minutes before the deadline")
    ap.add_argument("--families", default=None,
                    help="project families to open, comma-separated (alpha,beta,gamma) or 'all' for the "
                         "nine-project pool; default is the preset's list (the pilots so far: alpha only)")
    ap.add_argument("--rule-level", default=None,
                    help="the reason given for the laboratories' rule, one of the preset's `rule_texts` "
                         "(supplier form: approved_list, licence, injury); default is the preset's `rule_level`")
    ap.add_argument("--preregistration-ref", default=None,
                    help="the study's preregistration (a path from the repository root), which must declare "
                         "`STATUS: FINAL`; the run's manifest records it and its sha256")
    args = ap.parse_args()
    if args.preregistration_ref is not None:
        from oaos2.experiments.loader import validate_final_preregistration
        try:
            validate_final_preregistration(args.preregistration_ref)
        except (FileNotFoundError, ValueError) as exc:
            print(f"refused: {exc}")
            return 2
    org = load_org_spec(args.preset)
    if args.rule_level is not None:
        levels = (org.live_coordination or {}).get("rule_texts") or {}
        if args.rule_level not in levels:
            raise SystemExit(f"--rule-level {args.rule_level!r} is not one of {sorted(levels)} for {args.preset}")
        org = dataclasses.replace(org, live_coordination={**org.live_coordination, "rule_level": args.rule_level})
    families = None if args.families is None else [] if args.families.strip().lower() == "all" \
        else [f.strip() for f in args.families.split(",") if f.strip()]
    org = dataclasses.replace(org, live_coordination={**(org.live_coordination or {}), "instance_seed": args.seed,
                                                      **({"objective_text": ""} if args.no_objective else {}),
                                                      **({"families": families} if families is not None else {})})
    if args.minutes is not None:
        lc = dict(org.live_coordination)
        lc["bounds"] = {**dict(lc.get("bounds") or {}), "participant_deadline_s": float(args.minutes) * 60}
        org = dataclasses.replace(org, live_coordination=lc)
    wall_clock = wall_clock_for(org)
    deadline_min = float(((org.live_coordination or {}).get("bounds") or {}).get("participant_deadline_s", 600)) / 60
    print(f"series runs/{args.series}, preset {args.preset}, seed {args.seed}, deadline {deadline_min:g} min, families {(org.live_coordination or {}).get('families') or 'all nine projects'}, model {args.model}, {args.calls} calls per lab, cap ${args.cap:.0f}, "
          f"objective {"off" if args.no_objective else "stated" if (org.live_coordination or {}).get("objective_text") else "none"}, container lifetime {wall_clock} s, budget notice at {args.pressure:.0%}, context budget "
          f"{args.context_budget or [r.context_budget_tokens for r in org.roles]}")
    # The cap is a safety net, not a design parameter (September 26, 2026): the ledger admits a call only if
    # spend plus a worst-case projection for EVERY in-flight call fits under it, and refuses the next lab that
    # asks otherwise, silently retiring it. In the task-framing run of September 25 and the warm shakedown of
    # September 26 ($8 caps) this retired five and three labs, one of them the only lab that knew a qualifying
    # recipe, with budget left. Minimum: 1.25 times the expected spend (about $0.10 per lab-minute in the
    # PC1 runs) plus one worst-case call per lab.
    n_labs = len(org.roles)
    budget_tok = max([r.context_budget_tokens or 60000 for r in org.roles] + [args.context_budget or 0])
    # Priced from the model's own row (October 10, 2026; the guard had assumed Sonnet 4.6 prices), uncached input at
    # the longest prompt the context budget allows. The expected spend per lab-minute is scaled from the PC1 runs on
    # Sonnet 4.6 ($0.10) by the model's output price, the larger share of the bill; it is a guard, not an estimate.
    from oaos2.experiments.runner import _pricing_table_for
    row = _pricing_table_for([args.model]).price(args.model).for_prompt(budget_tok)
    worst_call = (budget_tok * row.input + args.max_output * row.output) / 1e6
    # October 16, 2026: scaled by output price alone, the guard expected $2 for MiniMax M3 runs that spent $5 by
    # minute 33; for these models the bill is mostly input. Observed spend per lab-minute in earlier runs of the same
    # model is used when there is any; otherwise the larger of the output-scaled figure and an input-inclusive one
    # (five calls a lab-minute of 15,000 input and 1,000 output tokens, uncached), both guards, not estimates.
    observed = None if args.guard_rate is not None else observed_spend_per_lab_minute(args.model, Path("runs"))
    priced = max(0.10 * row.output / 15.0, 5 * (15000 * row.input + 1000 * row.output) / 1e6)
    if args.guard_rate is not None:
        if not args.guard_rate > 0:
            print("refused: --guard-rate must be positive")
            return 2
        per_lab_minute = args.guard_rate
        basis = f"fixed at ${args.guard_rate:.4f} a lab-minute (--guard-rate)"
    else:
        per_lab_minute = observed[0] if observed else priced
        basis = (f"observed in {observed[1]} earlier run(s) of this model, at most ${observed[0]:.4f} a lab-minute"
                 if observed else f"priced, ${priced:.4f} a lab-minute (no earlier run of this model)")
    minimum = 1.25 * per_lab_minute * n_labs * deadline_min + n_labs * worst_call
    print(f"cap guard: expected spend about ${per_lab_minute * n_labs * deadline_min:.0f} ({basis}); minimum cap "
          f"${minimum:.0f} (1.25 x expected + {n_labs} worst-case calls of ${worst_call:.2f})")
    if args.cap < minimum and not args.allow_tight_cap:
        print("refused: the cap is below the guard's minimum and could retire labs mid-run; raise --cap or pass --allow-tight-cap")
        return 2
    # the reasoning settings the run will use, checked before anything is paid for (an effort model needs --effort)
    from oaos2.experiments.runner import _role_model_refs, _role_reasoning
    settings = _role_reasoning(_role_model_refs(org, args.model), reasoning_kind="thinking", reasoning_budget=args.reasoning_budget,
                               effort=args.effort)
    print("reasoning: " + "; ".join(sorted({f"{k} {v}" for r in settings.values() for k, v in r.items()
                                             if k in ("effort", "reasoning_budget") and v is not None})))
    if not args.go:
        print("dry run: pass --go to launch (paid, billed to your provider key)")
        return 0
    # A first SIGINT/SIGTERM stops the run cleanly (archive written, containers removed); a second forces an exit.
    stop = RunStop()
    install_signal_stop(stop)
    r = await run_org_live(
        org, RUNS / args.series, tier="main", model_ref=args.model, stop=stop,
        experiment_id=args.experiment or f"{args.preset}_s{args.seed}",
        task_pack=pack_for(org.live_coordination), cap_usd=args.cap, reasoning_kind="thinking", reasoning_budget=args.reasoning_budget, effort=args.effort,
        max_model_calls=args.calls, max_output_tokens=args.max_output, wall_clock_cap=wall_clock,
        budget_pressure_frac=args.pressure, context_budget=args.context_budget,
        preregistration_ref=args.preregistration_ref)  # recorded with its sha256
    print(f"run_dir {r.run_dir}\nclosed {r.closed} archive_valid {r.archive_valid} cost_usd {getattr(r, 'cost_usd', None)}")
    print("read it with: PYTHONPATH=\"$PWD\" python scripts/materials_lab_report.py " + str(Path(r.run_dir).parent))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
