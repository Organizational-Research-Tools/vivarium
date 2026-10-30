"""Task-generic exception vocabulary (platform_theory_audit.md §11.1).

An exception is a participant ACT: a structured record an agent commits when an
observed event requires a decision its ex ante rules do not cover (Galbraith's
referral unit; Perrow's exceptional case).  The platform owns only the record
SHAPE and its disposal discipline.  Whether a filed exception is GENUINE is
oracle-side (the schedule's researcher classification, environment/driver) and
is judged downstream by analysis — never at the gate, so gate feedback cannot
leak the classification (capture observables, compute constructs downstream).

Filing rides ordinary commitments (no new event class: the ``state.committed``
event IS the observable act); disposal rides the generic
``record_dispositions_cover`` conformance gate; queues and latencies are derived
projections in ``archive/exceptions.py``, never runtime state.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# The default disposal vocabulary.  ``repaired`` closes by naming its repair;
# ``referred`` closes THIS decision point while handing the exception upward or
# sideways (the projection keeps a referred exception pending organization-wide);
# ``dismissed`` closes by explicit reasoned rejection.  Packs may declare a
# different vocabulary on the gate; this is the foundation default.
EXCEPTION_DISPOSITIONS = ("repaired", "referred", "dismissed")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_unique_list(name: str, values: list[str]) -> list[str]:
    cleaned = [str(v).strip() for v in values]
    if any(not v for v in cleaned):
        raise ValueError(f"{name} entries must be nonempty")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{name} entries must be unique")
    return cleaned


class ExceptionRecord(StrictModel):
    """One filed exception.  ``exception_id`` is the stable join key that filing,
    routing, disposal, and archive analysis all share."""

    exception_id: str
    # Participant-vocabulary ids of the triggering observation(s) — the notice /
    # event ids the pack's materials use, NOT platform ULIDs.  The projection
    # joins them to schedule packets through the packet's declared ``refs``.
    trigger_refs: list[str] = Field(min_length=1)
    # The filer's CLAIM of which attention scopes a correct response touches.
    # Correctness of the claim is an analysis question, not a gate question.
    affected_scopes: list[str] = Field(min_length=1)
    # The ex ante rule the filer holds applicable, if any.  None asserts the
    # event is uncovered — the Galbraith exception claim itself.
    rule_ref: str | None = None
    summary: str
    # Study CH1 structured-template channel: a pack MAY declare a filing template
    # (manifest ``submission.exception_records.template``) whose named fields the
    # filer must fill. Absent a template the field is unused (today's free
    # summary). Field NAMES are channel form; their content is the filer's.
    template_fields: dict[str, str] | None = None

    @field_validator("exception_id", "summary")
    @classmethod
    def nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must be nonempty")
        return value

    @field_validator("rule_ref")
    @classmethod
    def nonempty_or_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("rule_ref must be nonempty or omitted")
        return value

    @field_validator("trigger_refs")
    @classmethod
    def clean_trigger_refs(cls, value: list[str]) -> list[str]:
        return _clean_unique_list("trigger_refs", value)

    @field_validator("affected_scopes")
    @classmethod
    def clean_affected_scopes(cls, value: list[str]) -> list[str]:
        return _clean_unique_list("affected_scopes", value)


class ExceptionReport(StrictModel):
    """The list shape a filing commitment carries.  [] is a legal report:
    'no exceptions this wave' is itself an observable act."""

    records: list[ExceptionRecord]

    @model_validator(mode="after")
    def unique_exception_ids(self):
        ids = [record.exception_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("exception_id values must be unique within a report")
        return self


def record_substantive_chars(record) -> int:
    """The characters the reporting norms count: a record's summary plus its template
    fields (the record model forbids any other free text)."""
    if not isinstance(record, dict):
        return 0
    fields = record.get("template_fields")
    summary = record.get("summary")
    return (len(summary) if isinstance(summary, str) else 0) + sum(
        len(v) for v in (fields.values() if isinstance(fields, dict) else ()) if isinstance(v, str))


def validate_exception_records(value, template: dict | None = None,
                               text_max_chars: int | None = None,
                               report_text_max_chars: int | None = None,
                               required_ids: list[str] | None = None) -> list[str]:
    """Shape-only problem list for a payload field holding exception records.

    Returns [] when conformant.  Messages describe the agent's own payload shape
    and never reference oracle classification.

    ``template`` (CH1 structured channel) = ``{fields: [name, ...], max_chars: N}``:
    every record must carry ``template_fields`` with exactly those names, each a
    nonempty string within ``max_chars``. ``text_max_chars`` (CH1, review rounds
    6–7) caps each record's SUBSTANTIVE TEXT — ``summary`` plus every
    ``template_fields`` value together — so the checklist and template arms have
    the same total reporting space (the template's summary counted, not left
    uncapped beside six capped fields). ``report_text_max_chars`` (CH2 workload
    design) caps the SUM of that substantive text over every record in the
    filing — the period report's one-page norm. ``required_ids`` (same design) names
    the cases the filing must carry a record for: coverage, not just a count.
    Judges no content.
    """
    if not isinstance(value, list):
        return [f"must be a list of exception records, got {type(value).__name__}"]
    try:
        ExceptionReport(records=value)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ()) if part != "records")
            problems.append(f"[{location}]: {error.get('msg', 'invalid')}")
        return problems
    problems: list[str] = []
    if template:
        problems.extend(_validate_template(value, template))
    _substantive = record_substantive_chars
    if required_ids:
        have = {str(r.get("exception_id", "")).strip() for r in value if isinstance(r, dict)}
        missing = [c for c in required_ids if c not in have]
        if missing:
            problems.append(f"no record for case(s) {missing}: one exception record per case you hold")
    if isinstance(text_max_chars, int):
        for index, record in enumerate(value):
            if not isinstance(record, dict):
                continue
            total = _substantive(record)
            if total > text_max_chars:
                problems.append(f"[{index}]: summary plus template fields run to {total} characters; "
                                f"the filing allows {text_max_chars} in all")
    if isinstance(report_text_max_chars, int):
        total = sum(_substantive(r) for r in value if isinstance(r, dict))
        if total > report_text_max_chars:
            problems.append(f"the report's records run to {total} characters of substantive text in all; "
                            f"the quarter report allows {report_text_max_chars}")
    return problems


def _validate_template(records: list, template: dict) -> list[str]:
    names = [str(n) for n in (template.get("fields") or [])]
    max_chars = template.get("max_chars")
    problems: list[str] = []
    for index, record in enumerate(records):
        fields = record.get("template_fields") if isinstance(record, dict) else None
        if not isinstance(fields, dict):
            problems.append(
                f"[{index}.template_fields]: required object with the fields "
                f"{names} (each a nonempty text)")
            continue
        missing = [n for n in names if not str(fields.get(n, "") or "").strip()]
        unknown = sorted(set(fields) - set(names))
        if missing:
            problems.append(f"[{index}.template_fields]: missing or empty {missing}")
        if unknown:
            problems.append(f"[{index}.template_fields]: unknown fields {unknown}")
        if isinstance(max_chars, int):
            over = [n for n in names
                    if isinstance(fields.get(n), str) and len(fields[n]) > max_chars]
            if over:
                problems.append(
                    f"[{index}.template_fields]: {over} exceed {max_chars} characters")
    return problems
