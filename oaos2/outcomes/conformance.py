"""Check submission structure and declared public constraints before acceptance.

Commitment.submission selects required fields, size limits, and consistency
checks. Registered task gates can check public budget or amendment requirements.
This is separate from judging hidden benefits, substantive correctness, or reason
quality. Only public information should be used in feedback from this gate."""

from __future__ import annotations

import inspect
import json
import math

from oaos2.protocols.exceptions import EXCEPTION_DISPOSITIONS, validate_exception_records


class CommitmentConformanceError(RuntimeError):
    """A commitment reached the single-writer boundary with an invalid payload."""

    def __init__(self, commitment_id: str, problems: list[str]):
        self.commitment_id = commitment_id
        self.problems = list(problems)
        super().__init__(f"commitment {commitment_id!r} is nonconformant: " + "; ".join(problems))


def _is_number(v) -> bool:
    if isinstance(v, bool):
        return False  # booleans are not numeric results
    if isinstance(v, (int, float)):
        return math.isfinite(v)  # NaN/inf are not results (they defeat every comparison)
    if isinstance(v, str):
        try:
            return math.isfinite(float(v))
        except (ValueError, TypeError):
            return False
    return False


# Open submission-gate registry (audit round 8 P1-2): task-owned gates live in
# plugins and register here — the manifest declares its gate modules
# (``submission_gates``), the loader imports them at pack load, and this core
# module enumerates NO task vocabulary (the amendment/allocation/case gates
# that used to live inline are budget-pack plugins now). A gate is
# ``fn(spec, payload, committed) -> list[str]`` of problem strings.
_TASK_GATES: dict[str, object] = {}

# The submission-format keys core itself interprets. Anything else in a
# declared ``fmt`` must be a registered task gate — an unowned key fails
# closed rather than silently pretending to bind (probe 2026-08-17).
_FOUNDATION_FMT_KEYS: frozenset[str] = frozenset({
    "format", "min_results", "required", "max_chars", "max_list_items",
    "require_number_map", "field_sum_max", "commitment_dispositions_cover",
    "exception_records", "record_dispositions_cover", "allowed_fields",
    # Declared in the same `submission` block but consumed by OTHER subsystems
    # (retry loop in agents/tools, slot-ceiling fallback and stage-duty notice
    # in the clocked runner) — legitimate here, not gate vocabulary.
    "max_retries", "ceiling_fallback", "duty_note",
    # The case file re-delivered with a disposition duty (outcomes/case_file.py).
    "case_file",
    # Restate this commitment and its duty note after a context compaction
    # (agents/model_agent.py; LK1, 2026-10-01). Opt-in per commitment.
    "restate_after_compaction",
})


def gate_kinds_registered_by(modules) -> frozenset[str]:
    """The gate kinds whose registering function lives in one of ``modules`` —
    the PROVENANCE view of the registry (probe round 2, 2026-08-17). The task
    loader validates a manifest's submission keys against foundation keys plus
    ONLY the gates its own declared ``submission_gates`` modules registered, so
    cross-pack gate borrowing and typo'd keys fail at LOAD, not mid-run."""
    mods = {str(mod) for mod in modules}
    return frozenset(kind for kind, fn in _TASK_GATES.items()
                     if getattr(fn, "__module__", None) in mods)


def register_submission_gate(kind: str, fn) -> None:
    """Register a task-owned submission gate for a declared ``fmt`` key.

    Idempotent for the same function (packs load repeatedly per sweep);
    refuses a CONFLICTING re-registration — two packs may not fight over one
    key, that is a naming bug worth failing loudly on.
    """
    existing = _TASK_GATES.get(kind)
    if existing is not None and existing is not fn:
        raise ValueError(f"submission gate {kind!r} already registered by "
                         f"{getattr(existing, '__module__', existing)!r}")
    _TASK_GATES[kind] = fn


_IDENT_MAX = 64


def _rule_ok(value, rule_ids: list) -> bool:
    """A rule may be cited by its full id (``R1_minor_cost_increase``) or by the short form
    the brief uses as its example (``R1``)."""
    if not isinstance(value, str):
        return False
    return value in rule_ids or any(r.split("_", 1)[0] == value for r in rule_ids)


def _scope_token(value: str) -> str:
    """Normalize an office reference to the canonical scope: 'Office of Economy', 'the
    economy office', 'economy', 'office/economy' → 'office/economy'. Non-office strings
    are returned lowercased and stripped, so a vocabulary check still rejects prose."""
    t = value.strip().lower()
    for prefix in ("office/", "office of ", "the office of ", "the "):
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    for suffix in (" office",):
        if t.endswith(suffix):
            t = t[: -len(suffix)].strip()
    return f"office/{t}" if t and " " not in t else t


def _identifier_problems(payload: dict, records, ident: dict) -> list[str]:
    """Problems for identifier and reference fields outside the declared vocabularies;
    ``ident`` = {office: [...], rule: [...], program: [...], rule_ref: [...], case_id: [...],
    notice_id: [...], scope: [...]}. Reference fields are vocabularies, not free text, so
    the report-wide norm cannot be evaded by splitting prose across them."""
    out: list[str] = []
    office = payload.get("office")
    if "office" in ident and office not in ident["office"]:
        out.append(f"office must be one of {ident['office']}, not {str(office)[:40]!r}")
    apps = payload.get("rule_applications")
    if apps is not None and not isinstance(apps, list):
        out.append("rule_applications must be a list of {rule, program} entries")
        apps = []
    for i, app in enumerate(apps or []):
        if not isinstance(app, dict):
            out.append(f"rule_applications[{i}] must be an object with rule and program")
            continue
        if "rule" in ident and not _rule_ok(app.get("rule"), ident["rule"]):
            out.append(f"rule_applications[{i}].rule must be a rule id (R1 … R6, or the full id)")
        if "program" in ident and app.get("program") not in ident["program"]:
            out.append(f"rule_applications[{i}].program must be a register program id")
    if not isinstance(records, list):
        return out
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        ref = rec.get("rule_ref")
        if "rule_ref" in ident and ref is not None and not _rule_ok(ref, ident["rule_ref"]):
            out.append(f"exception_records[{i}].rule_ref must be a rule id or null")
        vocab = {"exception_id": ident.get("case_id"), "trigger_refs": ident.get("notice_id"),
                 "affected_scopes": ident.get("scope")}
        for key, allowed in vocab.items():
            vals = rec.get(key)
            vals = vals if isinstance(vals, list) else [vals]
            for v in vals:
                if not isinstance(v, str):
                    continue
                # an office may be named as the brief's readers do — "economy", "Office of
                # Economy", "office/economy" (live pilot 2026-09-24: the canonical-form-only
                # gate refused every natural spelling and aborted four runs on retries)
                token = _scope_token(v) if key == "affected_scopes" else v.strip()
                if allowed is not None and token not in allowed:
                    out.append(f"exception_records[{i}].{key} must name a case, notice or office "
                               f"the materials use, not {v[:40]!r}")
                elif len(v) > _IDENT_MAX:
                    out.append(f"exception_records[{i}].{key} holds a {len(v)}-character value; "
                               f"identifiers are at most {_IDENT_MAX} characters")
    return out


def duty_cap_note(submission: dict | None) -> str:
    """The sentence a duty notice adds when the slot caps a record's free text.

    ``exception_records.text_max_chars`` is enforced at submission; before this note the
    packets told officers to keep "within the stated length" while no notice stated one
    (realism review 2026-09-25, defect 2). Empty when the slot sets no cap, so a slot
    without a cap promises nothing. Leading space, so it appends to a duty sentence."""
    er = (submission or {}).get("exception_records") or {}
    cap = er.get("text_max_chars")
    if not isinstance(cap, int) or cap <= 0:
        return ""
    return (f" The free text of your record (the summary and any remarks) is held to at most "
            f"{cap} characters in total; a longer record is not accepted.")


def check_conformance(payload, fmt: dict, *, committed: dict | None = None, commitment=None) -> tuple[bool, list[str]]:
    """Return (ok, problems) for ``payload`` against the declared submission format.

    ``fmt`` keys (all optional): ``format`` (only ``flat_numeric`` is foundation),
    ``min_results`` (default 1). Problems describe the AGENT's own payload shape only.
    An empty ``fmt`` accepts any JSON object without further field checks.

    ``committed`` (optional, {commitment_id: payload} of already-committed artifacts)
    enables the cross-commitment ``dispositions_cover`` gate. It checks that a disposition
    exists per amendment and that applied/partial labels agree with public allocation values;
    it requires but does not judge the content of an overrule reason.
    """
    if not isinstance(payload, dict):
        return False, [f"submission must be a JSON object, got {type(payload).__name__}"]
    if not fmt:
        return True, []
    kind = fmt.get("format", "flat_numeric")
    problems: list[str] = []

    if kind == "flat_numeric":
        nested = [k for k, v in payload.items() if isinstance(v, (dict, list))]
        if nested:
            problems.append(
                "submission must be a FLAT object (result_name -> number); nested values at: "
                + ", ".join(sorted(nested)[:10])
            )
        numeric_keys = [k for k, v in payload.items() if _is_number(v)]
        min_results = int(fmt.get("min_results", 1))
        if len(numeric_keys) < min_results:
            problems.append(
                f"need at least {min_results} numeric result value(s); found "
                f"{len(numeric_keys)} (submit result_name -> number pairs)"
            )
    elif kind == "structured":
        # A structured handoff/artifact: the declared fields must be PRESENT (by name —
        # field names are the agent's own, never answer values). The handoff-format gate
        # for the pipeline's reader→builder spec (DESIGN §12.2 HandoffFormatSpec).
        missing = [f for f in fmt.get("required", []) if f not in payload or payload[f] in (None, "")]
        if missing:
            problems.append("missing required field(s): " + ", ".join(sorted(missing)))
        # Field whitelist (CH2 workload design): a capped report may carry its text only in
        # the declared fields — an undeclared top-level field would carry it past the cap.
        allowed = fmt.get("allowed_fields")
        if allowed:
            unknown = sorted(set(payload) - set(allowed))
            if unknown:
                problems.append(
                    f"unexpected field(s) {unknown}: this submission carries only {list(allowed)}")
        # Size/arity caps are a mechanical compression treatment. They limit bytes and list
        # items but do not prove that any particular fact was lost: several facts may share
        # one item. Uncertainty absorption is therefore measured downstream from the trace.
        max_chars = fmt.get("max_chars")
        if max_chars:
            size = len(json.dumps(payload, sort_keys=True))
            if size > int(max_chars):
                problems.append(
                    f"submission too large: {size} chars serialized exceeds the {max_chars}-char "
                    "cap — compress to what the recipient actually needs"
                )
        for fname, cap in (fmt.get("max_list_items") or {}).items():
            v = payload.get(fname)
            if isinstance(v, list) and len(v) > int(cap):
                problems.append(
                    f"field {fname!r} has {len(v)} items; the cap is {cap} — keep only "
                    "the items that earn the space"
                )
        # Shape pin for award/allocation maps (budget_execution calibration round 1,
        # 2026-08-12): an undeclared shape let a run submit a LIST of
        # {program, amount, rationale} objects, which silently bypassed field_sum_max
        # (dict-only) and zero-scored at evaluation — a cold failure with no retry.
        # Declaring the field here makes the wrong shape retry-fixable, and the feedback
        # states only the expected SHAPE (public brief content), never hidden values.
        for fname in (fmt.get("require_number_map") or []):
            v = payload.get(fname)
            if v is None:
                continue  # presence is the `required` list's job, not this gate's
            ok_map = isinstance(v, dict) and all(
                isinstance(key, str) and _is_number(item) and float(item) >= 0
                for key, item in v.items())
            if not ok_map:
                problems.append(
                    f"field {fname!r} must be a single JSON object mapping id to a "
                    'nonnegative numeric amount (e.g. {"program_id": 12}) — no lists, '
                    "no nested objects; put rationale in its own field, never inside "
                    "the map")
        # Feasibility ceiling on a mapping field's numeric sum. The cap is PUBLIC task
        # content (the fund brief states it), so the feedback leaks nothing hidden, and an
        # infeasible package is retry-fixable arithmetic — exactly this gate's territory.
        # Each refusal is a recorded intervention (the compose-under-pressure overshoot
        # stays measurable), instead of a cold scored failure wasting the whole cell.
        for fname, cap in (fmt.get("field_sum_max") or {}).items():
            v = payload.get(fname)
            if isinstance(v, dict):
                total = 0.0
                for item in v.values():
                    try:
                        total += max(0.0, float(item))
                    except (TypeError, ValueError):
                        continue  # unparseable amounts are the evaluator's problem, not a sum
                if total > float(cap) + 1e-6:
                    # State the OVERAGE and the trim rule: without them, a budget-pressured
                    # agent reads "reduce to fit" as "slash" and guts the package (2026-07-05
                    # zero-cell autopsy: $433 → $92/$73 totals). Still shape-only — the cap
                    # and any per-item minimums are public task content.
                    problems.append(
                        f"field {fname!r} totals {total:g} — {total - float(cap):g} OVER the "
                        f"stated ceiling of {cap:g}. Trim roughly that amount, not more; if "
                        "items have stated minimums, DROP whole items below viability rather "
                        "than shaving every item"
                    )
        # Generic staged-record disposal gate: require one explicit procedural
        # disposition per source commitment.  Unlike the budget amendment gate above,
        # this judges no domain values; it only makes application/rejection visible and
        # complete before a later artifact can unblock.
        cdc = fmt.get("commitment_dispositions_cover")
        if cdc and committed is not None:
            field = cdc["field"]
            dispositions = payload.get(field)
            if not isinstance(dispositions, dict):
                problems.append(f"field {field!r} must be an object")
                dispositions = {}
            prefix = str(cdc.get("source_prefix", ""))
            owed = sorted(cid for cid in committed if cid.startswith(prefix))
            valid = tuple(cdc.get(
                "valid_dispositions",
                ["applied", "partially_applied", "superseded", "rejected"],
            ))
            for cid in owed:
                entry = dispositions.get(cid)
                if not isinstance(entry, dict) or entry.get("disposition") not in valid:
                    problems.append(
                        f"{field} is missing a valid entry for source commitment {cid!r}: "
                        f"{{disposition: one of {list(valid)}, reason: ...}}")
                    continue
                if not str(entry.get("reason", "")).strip():
                    problems.append(f"{field}[{cid!r}] requires a stated reason")
            extra = sorted(set(dispositions) - set(owed))
            if extra:
                problems.append(
                    f"{field} contains entries that are not source commitments for this "
                    f"stage: {extra}")
        # Task-generic exception filing gate (platform_theory_audit.md §11.1): the
        # declared field must hold ExceptionRecord-shaped items.  Shape-only — whether
        # a filed exception is GENUINE (vs rule-covered) is oracle-side and judged
        # downstream, so this feedback cannot leak the schedule classification.  An
        # explicit [] is legal by default: "no exceptions this wave" is itself the
        # observable act; a missing field is not.
        er = fmt.get("exception_records")
        if er:
            field = er.get("field", "exception_records")
            value = payload.get(field)
            if value is None:
                problems.append(
                    f"missing required field {field!r}: a list of exception records "
                    "([] if this wave surfaced none)")
            else:
                record_problems = validate_exception_records(
                    value, er.get("template"), er.get("text_max_chars"),
                    required_ids=er.get("required_ids"))
                problems.extend(
                    f"{field}{p}" if p.startswith("[") else f"{field}: {p}"
                    for p in record_problems)
                # Identifier vocabularies (CH2 workload design, review 2026-09-24): the
                # fields the report-wide norm does not count are held to declared identifiers
                # or short tokens, so prose cannot travel in `office`, a rule id, a program id,
                # `rule_ref`, `exception_id`, `trigger_refs` or `affected_scopes`.
                ident = er.get("identifiers")
                if isinstance(ident, dict):
                    problems.extend(_identifier_problems(payload, value, ident))
                elif payload.get("rule_applications") is not None and not isinstance(payload.get("rule_applications"), list):
                    problems.append("rule_applications must be a list of {rule, program} entries")
                # The report-wide norm counts every free-text character the report carries:
                # each record's substantive text plus any free text in rule-log entries
                # (their `rule` and `program` identifiers excluded). Counted only once the
                # records are well-shaped — a malformed record is shape feedback, not a crash.
                report_cap = er.get("report_text_max_chars")
                if isinstance(report_cap, int) and isinstance(value, list) and not record_problems:
                    from oaos2.protocols.exceptions import record_substantive_chars

                    def _free(obj) -> int:
                        if isinstance(obj, str):
                            return len(obj)
                        if isinstance(obj, dict):
                            return sum(_free(v) for v in obj.values())
                        if isinstance(obj, list):
                            return sum(_free(v) for v in obj)
                        return 0
                    apps = payload.get("rule_applications")
                    # only the entry's own rule and program identifiers are exempt; anything
                    # else in an entry, at any depth, is free text
                    rule_text = sum(_free({k: v for k, v in app.items() if k not in ("rule", "program")})
                                    for app in (apps if isinstance(apps, list) else [])
                                    if isinstance(app, dict))
                    total = sum(record_substantive_chars(r) for r in value) + rule_text
                    if total > report_cap:
                        problems.append(
                            f"the report's records and rule-log entries run to {total} characters of "
                            f"free text in all; the quarter report allows {report_cap}")
                min_records = int(er.get("min_records", 0))
                if isinstance(value, list) and len(value) < min_records:
                    problems.append(
                        f"field {field!r} needs at least {min_records} exception record(s)")
        # Respond-or-repair for exception records: one explicit disposition per record
        # filed across prior source commitments — the per-ITEM analogue of
        # commitment_dispositions_cover, and the anti-smoothing closure discipline
        # (an exception cannot dissolve; it must be repaired with a named repair,
        # referred onward, or dismissed for a stated reason).  Judges no content.
        rdc = fmt.get("record_dispositions_cover")
        if rdc and committed is not None:
            field = rdc["field"]
            dispositions = payload.get(field)
            if not isinstance(dispositions, dict):
                problems.append(f"field {field!r} must be an object")
                dispositions = {}
            prefix = str(rdc.get("source_prefix", ""))
            records_field = rdc.get("records_field", "exception_records")
            id_field = rdc.get("id_field", "exception_id")
            valid = tuple(rdc.get("valid_dispositions", list(EXCEPTION_DISPOSITIONS)))
            repaired_label = str(rdc.get("repaired_label", "repaired"))
            # Convergent filing is DESIGN INTENT, not an error: two offices seeing the
            # same case file under the same id (fund brief), so one disposition is owed
            # per unique id — never one per filing (external audit 2026-08-09 blocker 1:
            # the earlier duplicate-id refusal deadlocked every compliant split-exception
            # run at the plan gate, which the disposer could not fix).
            owed: dict[str, str] = {}
            for cid in sorted(committed):
                if not cid.startswith(prefix):
                    continue
                src = committed[cid]
                records = src.get(records_field) if isinstance(src, dict) else None
                for record in records if isinstance(records, list) else []:
                    if not isinstance(record, dict):
                        continue  # the filing gate already rejected malformed records
                    rid = str(record.get(id_field, "")).strip()
                    if rid:
                        owed.setdefault(rid, cid)
            for rid, cid in sorted(owed.items()):
                entry = dispositions.get(rid)
                if not isinstance(entry, dict) or entry.get("disposition") not in valid:
                    problems.append(
                        f"{field} is missing a valid entry for exception {rid!r} from "
                        f"{cid!r}: {{disposition: one of {list(valid)}, "
                        "reason/repair_ref: ...}}")
                    continue
                if entry["disposition"] == repaired_label:
                    repair_ref = str(entry.get("repair_ref", "")).strip()
                    if not repair_ref:
                        problems.append(
                            f"{field}[{rid!r}]: a {repaired_label!r} disposition must name "
                            "its repair_ref (the commitment or change implementing it)")
                    # Resolvability (calibration round 2, 2026-08-12): the archive-side
                    # delivery rule credits a repair only when repair_ref names a
                    # COMMITTED artifact; live agents wrote prose descriptions, which
                    # scored as dangling with no retry. Gate it here — the plan itself
                    # may implement the change, so the manifest whitelists its own id
                    # via repair_ref_allow. Feedback names only the agent's own slots.
                    elif rdc.get("repair_ref_resolvable") and (
                            repair_ref not in committed
                            and repair_ref not in (rdc.get("repair_ref_allow") or [])):
                        allowed = ", ".join(rdc.get("repair_ref_allow") or [])
                        problems.append(
                            f"{field}[{rid!r}]: repair_ref {repair_ref!r} does not name a "
                            "committed artifact — use the commitment id of the repair "
                            f"implementing it (a committed repair slot{', or ' + allowed if allowed else ''}); "
                            "describe the change itself in the plan or the record's own "
                            "fields, not in repair_ref")
                elif not str(entry.get("reason", "")).strip():
                    problems.append(
                        f"{field}[{rid!r}]: a {entry['disposition']!r} disposition "
                        "requires a stated reason")
            extra = sorted(set(dispositions) - set(owed))
            if extra:
                problems.append(f"{field} contains entries for unknown exception ids: {extra}")
        # Task-owned gates (open registry, audit round 8 P1-2): every key a
        # loaded pack registered dispatches to its plugin gate — the
        # amendment/allocation/case vocabulary that used to sit here lives in
        # the budget packs' plugin modules now.
        for _gate_kind, _gate_fn in sorted(_TASK_GATES.items()):
            _spec = fmt.get(_gate_kind)
            if _spec:
                kwargs = ({"commitment": commitment}
                          if "commitment" in inspect.signature(_gate_fn).parameters else {})
                problems.extend(_gate_fn(_spec, payload, committed, **kwargs))
        # A declared gate key nobody owns is an APPARATUS error (probe
        # 2026-08-17): silently ignoring it would let a manifest believe a
        # protection binds when nothing enforces it. Fail closed.
        unknown_keys = set(fmt) - _FOUNDATION_FMT_KEYS - set(_TASK_GATES)
        if unknown_keys:
            return False, [
                f"unknown submission-format keys {sorted(unknown_keys)} — not a "
                "foundation key and no loaded pack registered a gate for them"]
    else:  # a declared-but-unknown gate is an apparatus error; fail closed
        return False, [f"unknown submission format {kind!r}"]

    return (not problems), problems
