"""Check required research evidence before a confirmatory run starts.

Require a FINAL preregistration and declared calibration evidence matching the
task, models, and capacity conditions. Validate evidence files, content hashes,
and backing archives; do not infer readiness from missing baseline arms or
from a post-run check. Refuse deliberative modes that need the conversation
protections still listed as unimplemented in docs/mechanism/DEFERRED.md §7.

A passed check means these implemented prerequisites passed. It does not replace
materials review, establish every validity claim, or authorize a paid launch."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ConfirmatoryReadinessError(RuntimeError):
    """A confirmatory launch precondition is not met — refused BEFORE any
    cell, container, or spine exists."""


_EVIDENCE_KIND = "capacity_calibration"
_EVIDENCE_FIELDS = ("task_pack", "tier", "model_ref", "capacity_established",
                    "batch_ref")


def _load_evidence_doc(decl) -> dict:
    """One pinned evidence artifact → its validated doc (integrity + type +
    provenance linkage). Probe round 2 (2026-08-17): the doc is parsed from the
    SAME bytes that were hashed (no double read / TOCTOU), and it must link to
    a real calibration batch — a free-standing self-attested JSON blob is not
    evidence."""
    if not isinstance(decl, dict) or not decl.get("path") or not decl.get("sha256"):
        raise ConfirmatoryReadinessError(
            "confirmatory_evidence.capacity_calibration entries must be typed, "
            "hash-pinned declarations {path, sha256} — a bare file reference is "
            "not evidence (any existing file would pass)")
    path = Path(str(decl["path"]))
    if not path.is_file():
        raise ConfirmatoryReadinessError(
            f"capacity_calibration evidence {str(path)!r} does not exist — the "
            "premise must be backed by a real, referenceable artifact")
    data = path.read_bytes()  # hash and parse the SAME bytes (no second read)
    digest = hashlib.sha256(data).hexdigest()
    if digest != str(decl["sha256"]).strip().lower():
        raise ConfirmatoryReadinessError(
            f"capacity_calibration evidence {str(path)!r} does not match its "
            "declared sha256 — the artifact the claim rests on must be exactly "
            "the artifact that was pinned")
    try:
        doc = json.loads(data)
    except ValueError:
        raise ConfirmatoryReadinessError(
            f"capacity_calibration evidence {str(path)!r} is not a JSON "
            "artifact — evidence is typed, not prose") from None
    if not isinstance(doc, dict) or doc.get("kind") != _EVIDENCE_KIND:
        raise ConfirmatoryReadinessError(
            "capacity evidence must declare kind: capacity_calibration "
            f"(got {doc.get('kind') if isinstance(doc, dict) else type(doc).__name__!r})")
    missing = [k for k in _EVIDENCE_FIELDS if k not in doc]
    if missing:
        raise ConfirmatoryReadinessError(
            f"capacity evidence is missing required fields {missing} "
            "(task_pack / tier / model_ref / capacity_established / batch_ref)")
    # Estimand correction 2026-08-27 (FORM × REQUIREMENT): a tier's evidence
    # attests one of two VERDICTS, declared by role. "premise" (default,
    # legacy docs unchanged) attests the M7 §8 Q2 capacity premise — solo
    # bound on this tier. "manipulation_check" attests the LOW-requirement
    # tier's mirror criterion — capacity deliberately NOT exceeded (rules
    # absorb the load; c4 v2 §3). Either way the calibration must have
    # reached a definite verdict on real archives; what refuses is a
    # role↔verdict MISMATCH — in particular, a manipulation_check that found
    # solo bound is the design's halt-for-PI condition, never launch evidence.
    role = doc.get("role", "premise")
    if role not in ("premise", "manipulation_check"):
        raise ConfirmatoryReadinessError(
            f"capacity evidence declares unknown role {role!r} — "
            "one of: premise, manipulation_check")
    if role == "premise" and doc["capacity_established"] is not True:
        raise ConfirmatoryReadinessError(
            "capacity evidence records capacity_established != true — an "
            "unsuccessful or inconclusive calibration is not evidence")
    if role == "manipulation_check" and doc["capacity_established"] is not False:
        raise ConfirmatoryReadinessError(
            "manipulation_check evidence records capacity_established != false "
            "— a low-requirement tier on which capacity binds fails the "
            "manipulation check (c4 v2 §3): halt for PI disposition, do not "
            "mint launch evidence")
    _verify_batch_linkage(doc, evidence_path=path)
    return doc


# The backing archive's spine must end here: INV-5's sanctioned
# completed-superseded-by-failed shape means the run FAILED, and a failed or
# unterminated run cannot back a capacity premise.
_BACKING_TERMINAL = "run.completed"


def _archive_credentials(cell: Path, status: dict, doc: dict) -> str | None:
    """None when the archive at ``cell`` authentically backs ``doc``, else the
    first missing credential (surfaced in the refusal). Authenticity here is
    ARCHIVE SHAPE + CONSISTENCY (2026-08-27 critique round: a hand-typed
    three-field ``run_status.json`` used to pass): a valid, closed status, a
    manifest attesting the evidence's task pack, and a spine ending in a
    completed terminal. Not cryptographic provenance — there is no signed spend
    ledger — but forging it means forging a full archive, not one JSON stub."""
    if status.get("archive_valid") is not True:
        return "run_status.archive_valid is not true"
    if status.get("closed") is not True:
        return "run_status.closed is not true"
    try:
        manifest = json.loads((cell / "manifest.json").read_text())
    except (OSError, ValueError):
        return "no readable manifest.json beside run_status.json"
    if not isinstance(manifest, dict) or manifest.get("task_pack_id") != doc["task_pack"]:
        got = manifest.get("task_pack_id") if isinstance(manifest, dict) else None
        return (f"manifest.task_pack_id {got!r} does not attest the evidence's "
                f"task_pack {doc['task_pack']!r}")
    last = None
    try:
        with (cell / "trace" / "events.jsonl").open("rb") as fh:
            for line in fh:  # events can be MB-scale; a tail-seek could split a record
                if line.strip():
                    last = line
    except OSError:
        return "no readable trace/events.jsonl (an archive without a spine)"
    try:
        terminal = json.loads(last) if last else None
    except ValueError:
        return "trace/events.jsonl ends in an unparseable record"
    if not isinstance(terminal, dict) or terminal.get("event_class") != _BACKING_TERMINAL:
        got = terminal.get("event_class") if isinstance(terminal, dict) else None
        return (f"spine does not end in a {_BACKING_TERMINAL!r} terminal (got "
                f"{got!r}) — a failed or unterminated run cannot back the premise")
    return None


def _status_backs_model(status: dict, model_ref: str) -> bool:
    """A run backs the attested snapshot when it is the run-level ref, OR (per-role
    binding, C1h) when a role was bound to it AND that role actually spent — a
    gpt-5 office inside a Sonnet-factor run is live calibration of gpt-5, a
    declared-but-idle role is not. Falls back to the run's spend when the
    per-role partition is absent (pre-slice archives)."""
    if status.get("model_ref") == model_ref:
        return True
    roles = [r for r, m in (status.get("role_model_refs") or {}).items()
             if m == model_ref]
    if not roles:
        return False
    by_role = status.get("cost_by_role")
    if not isinstance(by_role, dict):
        return float(status.get("cost_usd") or 0) > 0
    return any(float(by_role.get(r) or 0) > 0 for r in roles)


def _verify_batch_linkage(doc: dict, *, evidence_path: Path) -> None:
    """The attested premise must be BACKED by real archives: ``batch_ref`` must
    resolve to a directory containing at least one run archive whose
    ``run_status.json`` records the attested model snapshot and tier with
    actual spend (a zero-cost stub archive is not a live calibration) AND that
    carries the archive credentials — valid+closed status, pack-attesting
    manifest, completed spine terminal (``_archive_credentials``). The
    pass/fail JUDGMENT stays the PI's — what is mechanical here is that the
    judgment points at archives with the shape only a real run produces, on the
    right snapshot."""
    raw = str(doc["batch_ref"])
    base = Path(raw)
    if not base.is_absolute():
        for root in (evidence_path.parent, Path.cwd()):
            if (root / raw).exists():
                base = root / raw
                break
    if not base.exists():
        raise ConfirmatoryReadinessError(
            f"capacity evidence batch_ref {raw!r} does not resolve to an "
            "existing calibration batch (tried absolute, evidence-relative, "
            "and cwd-relative)")
    statuses = ([base / "run_status.json"] if (base / "run_status.json").is_file()
                else sorted(base.rglob("run_status.json")))
    matched = False
    raw_setups = doc.get("setup_sha256s") or []
    if not isinstance(raw_setups, list) or not all(isinstance(x, str) for x in raw_setups):
        raise ConfirmatoryReadinessError("setup_sha256s must be a list of content hashes")
    required_setups = set(raw_setups)
    backed_setups = set()
    rejections: list[str] = []
    for status_path in statuses[:500]:
        try:
            status = json.loads(status_path.read_text())
        except (OSError, ValueError):
            continue
        if not (isinstance(status, dict)
                and _status_backs_model(status, doc["model_ref"])
                and status.get("difficulty") == doc["tier"]
                and float(status.get("cost_usd") or 0) > 0):
            continue  # cheap field triage first; credentials only on candidates
        why = _archive_credentials(status_path.parent, status, doc)
        if why is None:
            matched = True
            manifest = json.loads((status_path.parent / "manifest.json").read_text())
            setup = (manifest.get("extensions") or {}).get("research_setup_sha256")
            if setup in required_setups and manifest.get("mode") == "calibration":
                backed_setups.add(setup)
            if not required_setups or backed_setups == required_setups:
                break
        if len(rejections) < 5:
            rejections.append(f"{status_path.parent.name}: {why}")
    if matched and required_setups - backed_setups:
        raise ConfirmatoryReadinessError(
            f"capacity evidence setup hashes lack backing calibration archives: "
            f"{sorted(required_setups - backed_setups)}")
    if not matched:
        detail = ("; candidates refused: " + " | ".join(rejections)
                  if rejections else "")
        raise ConfirmatoryReadinessError(
            f"capacity evidence batch_ref {raw!r} contains no valid run archive "
            f"backing model_ref={doc['model_ref']!r}, difficulty={doc['tier']!r} "
            "with nonzero spend — required credentials: run_status "
            "archive_valid+closed, a manifest.json attesting this task_pack, "
            "and a spine ending in run.completed (the attested premise must be "
            f"backed by real live calibration archives){detail}")


def _validate_capacity_evidence(decl, *, task_pack=None, model_refs=(), tiers=(),
                                tier_roles=None) -> None:
    """The evidence must COVER the launch (probe round 2, 2026-08-17): every
    (model snapshot × tier) the design will actually run needs a validated,
    batch-linked artifact — membership of one attested snapshot among many
    launched is not coverage, and an empty launch set is a gate error, never a
    silent skip. ``tier_roles`` ({tier: premise|manipulation_check}, from
    ``confirmatory_evidence.capacity_roles``) additionally pins which VERDICT
    each launched tier's artifact must attest (external review 2026-08-27,
    finding 5)."""
    decls = decl if isinstance(decl, (list, tuple)) else [decl]
    docs = [_load_evidence_doc(d) for d in decls]
    for doc in docs:
        if task_pack and doc["task_pack"] != task_pack:
            raise ConfirmatoryReadinessError(
                f"capacity evidence is for task_pack {doc['task_pack']!r}, the "
                f"launch is {task_pack!r} — evidence does not transfer across packs")
    if not model_refs or not tiers:
        raise ConfirmatoryReadinessError(
            "confirmatory readiness cannot determine the launched model/tier "
            "set (empty) — declare explicit `model` and `difficulty` factors "
            "(or pass the cell's concrete model_ref/tier); evidence matching "
            "is never skipped")
    attested = {(d["model_ref"], d["tier"]) for d in docs}
    uncovered = [(m, t) for m in model_refs for t in tiers
                 if (m, t) not in attested]
    if uncovered:
        raise ConfirmatoryReadinessError(
            f"capacity evidence does not COVER the launch: missing attestation "
            f"for {uncovered} (attested: {sorted(attested)}) — every model "
            "snapshot × tier that runs confirmatory needs its own "
            "capacity-calibration artifact (M7 §8 Q2)")
    # Role coverage (external review 2026-08-27, finding 5): (model, tier)
    # membership alone would let a premise-labeled artifact satisfy a tier the
    # design needs the INVERTED verdict for. When the launch declares
    # tier_roles, every launched tier must be named and its docs' roles must
    # match; when it does not, only premise docs are acceptable (the legacy
    # single-verdict world) — a manipulation_check doc then REQUIRES the
    # declaration, so the expectation is always explicit, never inferred.
    doc_roles = {}
    for d in docs:
        doc_roles.setdefault(d["tier"], set()).add(d.get("role", "premise"))
    if tier_roles:
        unknown_role = {t: r for t, r in tier_roles.items()
                        if r not in ("premise", "manipulation_check")}
        if unknown_role:
            raise ConfirmatoryReadinessError(
                f"capacity_roles declares unknown roles {unknown_role} — "
                "one of: premise, manipulation_check")
        undeclared = [t for t in tiers if t not in tier_roles]
        if undeclared:
            raise ConfirmatoryReadinessError(
                f"capacity_roles declared but launched tiers {undeclared} have "
                "no entry — the expected verdict per tier is stated for the "
                "whole launch or not at all (fail-closed)")
        mismatched = {t: sorted(doc_roles.get(t, ()))
                      for t in tiers if doc_roles.get(t, set()) != {tier_roles[t]}}
        if mismatched:
            raise ConfirmatoryReadinessError(
                f"capacity evidence roles do not match the declared "
                f"capacity_roles: {mismatched} vs required "
                f"{ {t: tier_roles[t] for t in tiers} } — a tier the design "
                "expects inverted (manipulation_check) cannot be covered by a "
                "premise artifact, nor the reverse")
    else:
        check_only = [t for t in tiers if doc_roles.get(t) == {"manipulation_check"}
                      or "manipulation_check" in doc_roles.get(t, set())]
        if check_only:
            raise ConfirmatoryReadinessError(
                f"manipulation_check evidence for tiers {sorted(check_only)} "
                "requires the launch to declare capacity_roles (which tier "
                "expects which verdict) — the inverted-premise expectation is "
                "never inferred from the artifacts themselves")


def assert_confirmatory_ready(*, org_specs, preregistration_ref,
                              evidence: dict | None,
                              require_evidence: bool = True,
                              block_deferred_arms: bool = True,
                              task_pack: str | None = None,
                              model_refs=(), tiers=(), setup_sha256s=()) -> None:
    from oaos2.experiments.loader import validate_final_preregistration

    if not preregistration_ref:
        raise ConfirmatoryReadinessError(
            "confirmatory mode requires a preregistration_ref (§19)")
    validate_final_preregistration(preregistration_ref)

    if require_evidence:
        decl = (evidence or {}).get("capacity_calibration")
        if not decl:
            raise ConfirmatoryReadinessError(
                "confirmatory readiness requires declared capacity evidence: "
                "set confirmatory_evidence.capacity_calibration to the "
                "calibration artifact that re-established the single-agent-"
                "capacity premise (M7 §8 Q2) on the target model snapshot")
        roles = (evidence or {}).get("capacity_roles")
        if roles is not None and not isinstance(roles, dict):
            raise ConfirmatoryReadinessError(
                "confirmatory_evidence.capacity_roles must be a mapping "
                "{tier: premise|manipulation_check}")
        _validate_capacity_evidence(decl, task_pack=task_pack,
                                    model_refs=model_refs, tiers=tiers,
                                    tier_roles=roles)

    blocked = [o.preset_id for o in org_specs
               if block_deferred_arms
               and (o.live_coordination or {}).get("mode") == "deliberative"]
    if blocked:
        raise ConfirmatoryReadinessError(
            f"deliberative arms {blocked} cannot run confirmatory: the "
            "conversation-relay check, objective-disclosure check, and "
            "free-channel payload caps are DEFERRED (docs/mechanism/"
            "DEFERRED.md — required before that arm runs confirmatory; "
            "calibration may rely on post-hoc atom-trace detection)")

    if require_evidence:
        _require_setup_coverage(evidence, setup_sha256s)


def _require_setup_coverage(evidence, setup_sha256s):
    """Require exact resolved setups; an old pack name or capacity claim is insufficient."""
    if not setup_sha256s:
        raise ConfirmatoryReadinessError("confirmatory readiness requires resolved setup_sha256s")
    decl = evidence["capacity_calibration"]
    docs = [_load_evidence_doc(d) for d in (decl if isinstance(decl, (list, tuple)) else [decl])]
    covered = set()
    for doc in docs:
        hashes = doc.get("setup_sha256s")
        if (not isinstance(hashes, list) or not hashes
                or any(not isinstance(h, str) or len(h) != 71 or not h.startswith("sha256:")
                       or any(c not in "0123456789abcdef" for c in h[7:]) for h in hashes)):
            raise ConfirmatoryReadinessError(
                "capacity evidence needs setup_sha256s from newly matching calibration; "
                "legacy evidence does not authorize a changed setup")
        covered.update(hashes)
    missing = set(setup_sha256s) - covered
    if missing:
        raise ConfirmatoryReadinessError(f"capacity evidence does not cover resolved setups: {sorted(missing)}")
