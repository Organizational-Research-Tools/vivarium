"""Check declared comparison conditions and capacity results across runs.

Checks read result attributes without depending on the experiment runner's class.
They raise ConfoundViolation on a detected mismatch; the runner decides whether
to abort a confirmatory sweep or record a pilot violation. Capacity checks over
completed runs are distinct from the pre-run evidence validation in
experiments/confirmatory.py. Prior evidence is usable only when its model,
materials, and capacity settings match the proposed study."""

from __future__ import annotations


class ConfoundViolation(Exception):
    """A cross-condition constraint was violated; the sweep aborts (M7 §4)."""


# Recorded interventions that are PLATFORM-MECHANICAL (format/marker correction), not
# researcher treatment — excluded from the cross-arm recorded-rate gap so an arm whose
# roles naturally need more shape nudges isn't miscounted as "more intervened upon".
_MECHANICAL_KINDS = frozenset({
    "output_truncation_retry",  # max_tokens cutoff continuation (model_agent) — shape-only
    "submit_reminder",  # owed-submission prose nudge (model_agent) — shape-only
    "submission_nonconformant_retry",
    "marker_repair", "pause_timeout_stub",
})


def _distinct(results: list, attr: str) -> set:
    """Distinct non-None values of ``attr`` across cells (skips cells lacking it)."""
    return {v for r in results if (v := getattr(r, attr, None)) is not None}


def _intervention_counts(result) -> dict[str, int] | None:
    """Count ``intervention.recorded`` events per class for a cell from its archive.

    Returns None if the cell carries no readable ``run_dir`` (duck-typing tolerance),
    so this stays usable with synthetic CellResults in tests.
    """
    run_dir = getattr(result, "run_dir", None)
    if run_dir is None:
        return None
    try:
        from oaos2.trace.invariants import load_all_events

        events = load_all_events(run_dir)
    except Exception:  # pragma: no cover - missing/partial archive
        return None
    counts: dict[str, int] = {}
    mechanical = 0  # platform format/marker corrections, NOT researcher interventions
    for e in events:
        if e.get("event_class") == "intervention.recorded":
            p = e.get("payload") or {}
            cls = p.get("class", "recorded")
            counts[cls] = counts.get(cls, 0) + 1
            if cls == "recorded" and p.get("kind") in _MECHANICAL_KINDS:
                mechanical += 1
    counts["_mechanical_recorded"] = mechanical
    return counts


def realized_role_model_refs(events: list) -> dict:
    """``{agent_id: sorted distinct model_refs}`` actually dispatched, read from the
    spine's ``model.invoked`` events (the gateway stamps ``agent_id`` + ``payload.model_ref``
    on every call). Roles that never invoked a model are absent, not empty."""
    seen: dict[str, set] = {}
    for e in events:
        if e.get("event_class") != "model.invoked":
            continue
        agent, ref = e.get("agent_id"), (e.get("payload") or {}).get("model_ref")
        if agent and ref:
            seen.setdefault(agent, set()).add(ref)
    return {a: sorted(refs) for a, refs in sorted(seen.items())}


def certify_role_model_refs(events: list, declared: dict) -> dict:
    """Realized-vs-declared certificate for the per-role model binding (C1h): every
    role that invoked a model must have invoked EXACTLY its declared ref, and no
    undeclared agent may have invoked one. A mismatch is an apparatus fault (the
    runner bound a role to a model the manifest does not claim), raised as a
    ConfoundViolation like every other cross-condition gate. Returns the realized map."""
    realized = realized_role_model_refs(events)
    mismatched = {a: {"declared": declared.get(a), "realized": refs}
                  for a, refs in realized.items()
                  if a not in declared or refs != [declared[a]]}
    if mismatched:
        raise ConfoundViolation(
            f"role model binding mismatch (apparatus fault): realized != declared "
            f"for {mismatched}; declared map {declared}")
    return realized


def confound_check(results: list, *, mode: str = "pilot") -> dict:
    """Gate the compared cells. Raises ConfoundViolation on any violation.

    Returns a facts dict (intervention rates per cell) the caller can surface — an
    intervention-rate *imbalance* across arms is a confound to flag for researcher
    judgment (different arms legitimately intervene at different rates), whereas a
    ``treatment_defining`` intervention outside a declared treatment is a hard
    confirmatory violation (M7 §4).
    """
    if not results:
        raise ConfoundViolation("no cells to compare")

    # Same model snapshot across compared conditions (hard gate, §19).
    models = {r.model_ref for r in results}
    if len(models) != 1:
        raise ConfoundViolation(f"model snapshot differs across cells: {models}")

    # Per-role binding (C1h): the map IS the preset's treatment, so cells of ONE
    # preset must carry identical maps — a preset whose roles ran on different
    # models across replications is two conditions wearing one name. Maps
    # legitimately differ ACROSS presets (hSX vs hXS); the run-level ref above
    # is what roles inherit. Skipped for cells lacking the field (legacy duck-typing).
    maps_by_preset: dict[str, set] = {}
    for r in results:
        m = getattr(r, "role_model_refs", None)
        if m:
            maps_by_preset.setdefault(r.preset_id, set()).add(tuple(sorted(m.items())))
    split = {pid: [dict(t) for t in sorted(maps)]
             for pid, maps in sorted(maps_by_preset.items()) if len(maps) > 1}
    if split:
        raise ConfoundViolation(f"role model binding differs across cells of one preset: {split}")

    # Identical pricing-table across compared cells — usd-basis parity is meaningless
    # if the price table drifted between runs (DESIGN §15, M7 §4). Version AND hash:
    # the version is the declared identity, the hash catches an in-place edit at a
    # fixed version. (Skipped only if no cell carries the field — legacy duck-typing.)
    versions = _distinct(results, "pricing_table_version")
    if len(versions) > 1:
        raise ConfoundViolation(f"pricing-table version differs across cells: {versions}")
    hashes = _distinct(results, "pricing_table_hash")
    if len(hashes) > 1:
        raise ConfoundViolation(f"pricing-table hash differs across cells (same version edited?): {hashes}")

    # Identical cache-breakpoint policy across cells — differing placement changes the
    # cache hit rate → realized usd → silently breaks usd-basis parity (M3 §3.1). Only
    # live cells carry a fingerprint; offline cells (no model calls) carry None and are
    # exempt, but live cells must agree with each other.
    cache_fps = _distinct(results, "cache_policy_fingerprint")
    if len(cache_fps) > 1:
        raise ConfoundViolation(f"cache-breakpoint policy differs across cells: {cache_fps}")

    # No exposure-confounded cell may enter a CONFIRMATORY comparison (M3 §2.1): a cell
    # whose requested exposure was not satisfiable (e.g. a non-LCD cross-provider cell)
    # is refused at the sweep boundary, not silently compared.
    if mode == "confirmatory":
        confounded = [r.preset_id for r in results if getattr(r, "exposure_confounded", False)]
        if confounded:
            raise ConfoundViolation(f"exposure-confounded cells in confirmatory comparison: {confounded}")

    # Every compared cell must produce a coherent archive (archive-validity).
    invalid = [r.preset_id for r in results if not r.archive_valid]
    if invalid:
        raise ConfoundViolation(f"archive invalid for cells: {invalid}")

    # Closure and evaluator completion are separate. A closed outcome with a missing
    # headline evaluation is unscored, never a zero.
    unscored = [r.preset_id for r in results
                if not r.closed or not getattr(r, "scored", True)]
    if unscored:
        raise ConfoundViolation(f"cells did not close/score: {unscored}")

    # Confirmatory runtime gate (DESIGN §10.1/§24): only the host-owned raw_api loop
    # is permitted; tool_runner/custom are barred (mechanical enforcement, not
    # author discipline). FAIL-CLOSED: an unstamped cell (runtime=None — a legacy,
    # synthetic, or offline-stub result) is barred too — a gate that passes on a
    # missing field is author discipline in disguise.
    if mode == "confirmatory":
        bad_runtime = [r.preset_id for r in results
                       if getattr(r, "runtime", None) != "raw_api"]
        if bad_runtime:
            raise ConfoundViolation(
                f"non-raw_api (or unstamped) runtime barred in confirmatory cells: {bad_runtime}"
            )

    # Intervention accounting (M7 §4). treatment_defining outside a declared treatment
    # is a HARD confirmatory violation; the per-class rates are returned for the caller
    # to flag an imbalance.
    rates: dict[str, dict] = {}
    by_preset: dict[str, list[dict[str, int]]] = {}
    td_offenders: list[str] = []
    for index, r in enumerate(results):
        counts = _intervention_counts(r)
        if counts is None:
            continue
        run_dir = getattr(r, "run_dir", None)
        cell_id = str(run_dir) if run_dir is not None else f"{r.preset_id}#{index + 1}"
        rates[cell_id] = {"preset_id": r.preset_id, **counts}
        by_preset.setdefault(r.preset_id, []).append(counts)
        declared = set(getattr(r, "declared_treatments", []) or [])
        if mode == "confirmatory" and counts.get("treatment_defining", 0) > 0 and not declared:
            td_offenders.append(cell_id)
    if td_offenders:
        raise ConfoundViolation(
            f"treatment_defining interventions outside a declared treatment "
            f"(confirmatory): {td_offenders}"
        )

    # The cross-arm recorded-rate gap counts SUBSTANTIVE interventions only — platform
    # format/marker corrections (submission-conformance retries, marker repair, pause
    # timeout stubs) are mechanical and arm-dependent (decomposed roles emit more shape
    # nudges than a single replicator), so conflating them inflates the gap with a benign
    # signal. They are reported separately, not as researcher-intervention imbalance.
    def _mean(pid: str, key: str) -> float:
        cells = by_preset[pid]
        return sum(c.get(key, 0) for c in cells) / len(cells)

    recorded_rates = {
        pid: _mean(pid, "recorded") - _mean(pid, "_mechanical_recorded")
        for pid in by_preset
    }
    mechanical_rates = {pid: _mean(pid, "_mechanical_recorded") for pid in by_preset}
    aggregate = {}
    for pid, cells in by_preset.items():
        keys = sorted({key for counts in cells for key in counts})
        aggregate[pid] = {
            "n_cells": len(cells),
            "totals": {key: sum(c.get(key, 0) for c in cells) for key in keys},
            "mean_per_cell": {
                key: sum(c.get(key, 0) for c in cells) / len(cells) for key in keys},
        }
    return {
        "intervention_rates": rates,
        "intervention_rates_by_preset": aggregate,
        "recorded_rate_gap": (max(recorded_rates.values()) - min(recorded_rates.values()))
        if recorded_rates else 0,
        "substantive_recorded_rates": recorded_rates,
        "mechanical_recorded_rates": mechanical_rates,
    }


def single_agent_capacity_check(results_by_preset: dict) -> dict:
    """The hard precondition (§4/§8 Q2): the task genuinely exceeds one agent's
    capacity AND is not trivially solved by context expansion.

    Returns ``{premise_holds, ...}``; raises ConfoundViolation if the premise fails
    (recalibrate difficulty before any confirmatory run).
    """
    single = results_by_preset.get("single_agent")
    expanded = results_by_preset.get("context_expanded_single_agent")
    if single is None or expanded is None:
        raise ConfoundViolation("capacity check needs single_agent + context_expanded_single_agent arms")

    def _cells(value):
        return list(value) if isinstance(value, (list, tuple)) else [value]

    singles = _cells(single)
    expandeds = _cells(expanded)
    if not singles or not expandeds:
        raise ConfoundViolation("capacity check received empty baseline replication sets")
    if any(not getattr(r, "scored", True) for r in singles + expandeds):
        raise ConfoundViolation("capacity check includes an unscored baseline replication")

    # Hard, replication-level premise: neither baseline may solve the task in any
    # preregistered replication. This is intentionally conservative and avoids choosing
    # one arbitrary 'representative' cell from a batch.
    single_passes = sum(bool(r.passed) for r in singles)
    expanded_passes = sum(bool(r.passed) for r in expandeds)
    single_fails = single_passes == 0
    expansion_not_trivial = expanded_passes == 0
    premise_holds = single_fails and expansion_not_trivial
    facts = {
        "single_agent_fails": single_fails,
        "context_expansion_not_trivial": expansion_not_trivial,
        "single_agent_n": len(singles),
        "single_agent_passes": single_passes,
        "context_expanded_n": len(expandeds),
        "context_expanded_passes": expanded_passes,
        "premise_holds": premise_holds,
    }
    if not premise_holds:
        raise ConfoundViolation(
            "single-agent-capacity premise failed — recalibrate difficulty before any "
            f"confirmatory run: {facts}"
        )
    return facts
