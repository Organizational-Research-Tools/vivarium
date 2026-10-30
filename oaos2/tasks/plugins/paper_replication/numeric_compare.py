"""``numeric_compare`` evaluator — faithful port of the OLD platform's scorer.

This is the **fidelity-critical** asset (M7 §2.3): if it scores even slightly
differently from the calibrated old platform, it is a different task. It is a
verbatim port of `oaos/tasks/paper_replication.py::_check_success_against` (+
`_compare_result`, `_compare_against_alternative`, `_flatten_results`) and the
`KeyNormalizer` (`key_normalization.py`). The golden test
(`tests/experiments/test_numeric_compare_golden.py`) pins scores taken
independently from the OLD scorer and asserts this port reproduces them.

Scoring (unchanged from the old platform):
- matching order: exact → aliases → normalized → table-prefix → fuzzy (Jaccard,
  ≥0.5 medium / ≥0.8 high) → value-based second pass;
- per-result `tolerance_type` (percentage default, absolute, sign_match,
  exact_match, boolean, min/max_threshold) + `weight`; `alternatives` = OR-logic;
- `partial_score = weighted_matches / total_weight`; `passed = partial_score ≥ 0.99`;
- **multi-path best-of** across `expected_results.json` + `expected_results_ambiguous.json`
  (highest `partial_score`, tie-break lowest `mean_weighted_deviation`).

The hidden reference files are hash-pinned and host-only (never agent-visible).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from oaos2.evaluation.plugin_interface import EvaluatorInputRef, RawEvaluation
from oaos2.library import library_dir
from oaos2.tasks.plugins.paper_replication.key_normalization import (
    KeyNormalizer,
    extract_leading_number,
)

# Hidden references (answer keys) live in the config LIBRARY (data), not in this
# plugin's package — host-only, NEVER staged into a run's visible zone or mounted
# into a container (§8). The plugin reads the canonical library location, so the
# code carries no answer data and a different pack resolves its own refs.
# Resolved at CALL time (not import) so OAOS2_LIBRARY set after import is honored —
# matching the loaders; computing these at import would silently use stale paths.
def _hidden_dir() -> "Path":
    return library_dir() / "tasks" / "paper_replication" / "assets" / "hidden"


def _reference_path() -> "Path":
    return _hidden_dir() / "expected_results.json"


def _ambiguous_path() -> "Path":
    return _hidden_dir() / "expected_results_ambiguous.json"

# Pinned sha256 of the calibrated reference files — verified at load (M7 §2.2).
REFERENCE_SHA256 = "sha256:84b17487ff115d95101da1555cea94d35fb53d00a459514f7882a8d7e2f6145d"
AMBIGUOUS_SHA256 = "sha256:2b84421568376bd6f3b4f8b3e19cc7bff113a1e7af6d1955374e6e02da411dc9"

PASS_THRESHOLD = 0.99  # partial_score >= 0.99 (old platform's strict success bar)

_normalize_key = KeyNormalizer.normalize
_compute_key_similarity = KeyNormalizer.compute_similarity


class ReferenceHashMismatch(Exception):
    """A hidden reference was edited — refuse to run (no longer the calibrated task)."""


# --------------------------------------------------------------------------- #
# Scoring types (ported from oaos/core/types.py)
# --------------------------------------------------------------------------- #


class ToleranceType(str, Enum):
    PERCENTAGE = "percentage"
    RELATIVE = "relative"  # alias for percentage
    ABSOLUTE = "absolute"
    SIGN_MATCH = "sign_match"
    EXACT_MATCH = "exact_match"
    BOOLEAN = "boolean"
    CI_OVERLAP = "ci_overlap"
    MAX_THRESHOLD = "max_threshold"
    MIN_THRESHOLD = "min_threshold"


@dataclass
class ExpectedResult:
    name: str
    value: Any
    result_type: str = "numeric"
    tolerance_type: ToleranceType = ToleranceType.PERCENTAGE
    tolerance: float = 0.05
    weight: float = 1.0
    aliases: list[str] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ResultComparison:
    name: str
    expected: Any
    actual: Any
    tolerance_type: ToleranceType
    tolerance: float
    within_tolerance: bool
    deviation: float
    weight: float = 1.0


@dataclass
class SuccessCheck:
    passed: bool
    partial_score: float
    mean_weighted_deviation: float
    details: dict[str, ResultComparison]
    selected_variant: str | None = None
    variant_evaluations: dict[str, dict[str, float]] = field(default_factory=dict)
    unmatched_submitted_keys: list[str] = field(default_factory=list)
    matched_via: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Loading + hashing
# --------------------------------------------------------------------------- #


def _verify(path: Path, expected_sha: str) -> bytes:
    data = path.read_bytes()
    actual = "sha256:" + hashlib.sha256(data).hexdigest()
    if actual != expected_sha:
        raise ReferenceHashMismatch(f"{path.name}: expected {expected_sha}, got {actual}")
    return data


def _parse_expected(raw: dict) -> list[ExpectedResult]:
    out: list[ExpectedResult] = []
    for r in raw["results"]:
        out.append(
            ExpectedResult(
                name=r["name"],
                value=r.get("value"),
                result_type=r.get("type", "numeric"),
                tolerance_type=ToleranceType(r.get("tolerance_type", "percentage")),
                tolerance=r.get("tolerance", 0.05),
                weight=r.get("weight", 1.0),
                aliases=r.get("aliases", []),
                alternatives=r.get("alternatives", []),
            )
        )
    return out


def load_reference() -> dict:
    """Load + hash-verify the primary reference (the calibrated answer key)."""
    return json.loads(_verify(_reference_path(), REFERENCE_SHA256))


def load_expected_variants() -> dict[str, list[ExpectedResult]]:
    """Load all hash-verified expected-results variants for multi-path best-of."""
    variants = {"expected_results": _parse_expected(json.loads(_verify(_reference_path(), REFERENCE_SHA256)))}
    if _ambiguous_path().exists():
        variants["expected_results_ambiguous"] = _parse_expected(
            json.loads(_verify(_ambiguous_path(), AMBIGUOUS_SHA256))
        )
    return variants


def reference_input_ref() -> EvaluatorInputRef:
    return EvaluatorInputRef(ref=str(_reference_path()), content_hash=REFERENCE_SHA256)


# --------------------------------------------------------------------------- #
# Flatten (ported from _flatten_results)
# --------------------------------------------------------------------------- #

import re  # noqa: E402

_NESTED_KEYS = ["parameter_values", "results", "values", "estimates", "statistics"]


def _flatten_results(results: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}

    def _add_with_variants(key: str, value: Any) -> None:
        if isinstance(value, str):
            try:
                value = float(value)
            except (ValueError, TypeError):
                pass
        if not isinstance(value, (int, float, str, bool)):
            return
        flat[key] = value
        m = re.match(r"table_?\d+_column_?(\d+)_(.+)", key.lower())
        if m:
            flat[f"col{m.group(1)}_{m.group(2)}"] = value
        m = re.match(r"column_?(\d+)_(.+)", key.lower())
        if m:
            flat[f"col{m.group(1)}_{m.group(2)}"] = value

    def _flatten_recursive(d: dict[str, Any], prefix: str = "") -> None:
        for key, value in d.items():
            full_key = f"{prefix}_{key}" if prefix else key
            if isinstance(value, dict):
                key_lower = key.lower()
                if key_lower in _NESTED_KEYS:
                    _flatten_recursive(value, "")
                elif re.match(r"(table_?\d+|column_?\d+|col\d+)", key_lower):
                    _flatten_recursive(value, full_key)
                else:
                    _flatten_recursive(value, full_key)
            elif isinstance(value, (int, float, str, bool)):
                _add_with_variants(full_key, value)

    _flatten_recursive(results)
    return flat


# --------------------------------------------------------------------------- #
# Comparison (ported from _compare_result / _compare_against_alternative)
# --------------------------------------------------------------------------- #


def _compare(name: str, value: Any, tolerance_type: ToleranceType, tolerance: float,
             weight: float, actual: Any) -> ResultComparison:
    if actual is not None and isinstance(actual, str):
        try:
            actual = float(actual)
        except (ValueError, TypeError):
            extracted = extract_leading_number(actual)
            if extracted is not None:
                actual = extracted

    if actual is None or not isinstance(actual, (int, float, bool)):
        return ResultComparison(name, value, actual, tolerance_type, tolerance, False, 1.0, weight)

    if tolerance_type in (ToleranceType.PERCENTAGE, ToleranceType.RELATIVE):
        deviation = (abs(actual) if actual != 0 else 0.0) if value == 0 else abs(actual - value) / abs(value)
        within = deviation <= tolerance
    elif tolerance_type == ToleranceType.ABSOLUTE:
        deviation = abs(actual - value)
        within = deviation <= tolerance
    elif tolerance_type == ToleranceType.SIGN_MATCH:
        es = 1 if value > 0 else (-1 if value < 0 else 0)
        as_ = 1 if actual > 0 else (-1 if actual < 0 else 0)
        within = es == as_
        deviation = 0.0 if within else 1.0
    elif tolerance_type == ToleranceType.EXACT_MATCH:
        within = actual == value
        deviation = 0.0 if within else 1.0
    elif tolerance_type == ToleranceType.BOOLEAN:
        within = bool(actual) == bool(value)
        deviation = 0.0 if within else 1.0
    elif tolerance_type == ToleranceType.MAX_THRESHOLD:
        within = actual <= value
        deviation = max(0.0, actual - value) / abs(value) if value != 0 else abs(actual)
    elif tolerance_type == ToleranceType.MIN_THRESHOLD:
        within = actual >= value
        deviation = max(0.0, value - actual) / abs(value) if value != 0 else abs(actual)
    else:
        deviation = (abs(actual) if actual != 0 else 0.0) if value == 0 else abs(actual - value) / abs(value)
        within = deviation <= tolerance
    return ResultComparison(name, value, actual, tolerance_type, tolerance, within, deviation, weight)


def _compare_result(expected: ExpectedResult, actual: Any) -> ResultComparison:
    return _compare(expected.name, expected.value, expected.tolerance_type,
                    expected.tolerance, expected.weight, actual)


def _compare_against_alternative(alt: dict[str, Any], actual: Any, expected: ExpectedResult) -> ResultComparison:
    alt_tol = alt.get("tolerance", expected.tolerance)
    alt_tt = ToleranceType(alt.get("tolerance_type", expected.tolerance_type.value))
    cmp = _compare(expected.name, alt["value"], alt_tt, alt_tol, expected.weight, actual)
    return cmp


# --------------------------------------------------------------------------- #
# The scorer (ported verbatim from _check_success_against)
# --------------------------------------------------------------------------- #


def _check_success_against(expected_results: list[ExpectedResult], result: Any) -> SuccessCheck:
    if not isinstance(result, dict):
        return SuccessCheck(False, 0.0, 1.0, {})

    result = _flatten_results(result)
    details: dict[str, ResultComparison] = {}
    total_weight = 0.0
    weighted_matches = 0.0
    weighted_deviation = 0.0
    matched_submitted_keys: set[str] = set()
    matched_via: dict[str, tuple[str | None, str | None]] = {}

    for expected in expected_results:
        if expected.alternatives:
            best_match = None
            primary_actual = result.get(expected.name)
            if primary_actual is None:
                primary_normalized = _normalize_key(expected.name)
                for submitted_key in result:
                    if submitted_key in matched_submitted_keys:
                        continue
                    if _normalize_key(submitted_key) == primary_normalized:
                        primary_actual = result[submitted_key]
                        break
            if primary_actual is not None:
                for alt in expected.alternatives:
                    comparison = _compare_against_alternative(alt, primary_actual, expected)
                    if comparison.within_tolerance:
                        best_match = (expected.name, primary_actual, comparison)
                        break
            if best_match is None:
                for alt in expected.alternatives:
                    alt_name = alt["name"]
                    actual = result.get(alt_name)
                    alt_matched_key = None
                    if actual is not None:
                        alt_matched_key = alt_name
                    else:
                        alt_normalized = _normalize_key(alt_name)
                        for submitted_key in result:
                            if submitted_key in matched_submitted_keys:
                                continue
                            if _normalize_key(submitted_key) == alt_normalized:
                                actual = result[submitted_key]
                                alt_matched_key = submitted_key
                                break
                    if actual is not None:
                        comparison = _compare_against_alternative(alt, actual, expected)
                        if comparison.within_tolerance:
                            best_match = (alt_matched_key, actual, comparison)
                            break
            if best_match:
                matched_key, actual, comparison = best_match
                details[expected.name] = comparison
                weighted_matches += expected.weight
                matched_submitted_keys.add(matched_key)
                matched_via[expected.name] = (matched_key, "alternative")
            else:
                alt_values = [alt.get("value") for alt in expected.alternatives]
                submitted_key_for_alternatives = expected.name if primary_actual is not None else None
                seen_formatted: dict[str, str] = {}
                for v in alt_values:
                    formatted = f"{v:.3f}" if isinstance(v, (int, float)) else str(v)
                    seen_formatted.setdefault(formatted, formatted)
                alt_values_str = " or ".join(seen_formatted.values())
                min_deviation = 1.0
                if primary_actual is not None:
                    try:
                        actual_num = float(primary_actual)
                        for alt in expected.alternatives:
                            exp_val = alt.get("value")
                            if exp_val is not None:
                                try:
                                    exp_num = float(exp_val)
                                    dev = abs(actual_num - exp_num) / abs(exp_num) if exp_num != 0 else abs(actual_num)
                                    min_deviation = min(min_deviation, dev)
                                except (ValueError, TypeError):
                                    pass
                    except (ValueError, TypeError):
                        pass
                details[expected.name] = ResultComparison(
                    expected.name, alt_values_str, primary_actual, expected.tolerance_type,
                    expected.tolerance, False, min_deviation, expected.weight,
                )
                if submitted_key_for_alternatives:
                    matched_submitted_keys.add(submitted_key_for_alternatives)
                    matched_via[expected.name] = (submitted_key_for_alternatives, "alternative_no_match")
                else:
                    matched_via[expected.name] = (None, None)
            total_weight += expected.weight
            weighted_deviation += details[expected.name].deviation * expected.weight
            continue

        # Standard matching (no alternatives)
        actual = result.get(expected.name)
        matched_key = None
        match_type = None
        if actual is not None:
            matched_key, match_type = expected.name, "primary"
        if actual is None and expected.aliases:
            for alias in expected.aliases:
                actual = result.get(alias)
                if actual is not None:
                    matched_key, match_type = alias, "alias"
                    break
        if actual is None:
            expected_normalized = _normalize_key(expected.name)
            for submitted_key in result:
                if _normalize_key(submitted_key) == expected_normalized:
                    actual = result[submitted_key]
                    matched_key, match_type = submitted_key, "normalized"
                    break
        if actual is None and expected.aliases:
            for alias in expected.aliases:
                alias_normalized = _normalize_key(alias)
                for submitted_key in result:
                    if _normalize_key(submitted_key) == alias_normalized:
                        actual = result[submitted_key]
                        matched_key, match_type = submitted_key, "normalized_alias"
                        break
                if actual is not None:
                    break
        if actual is None:
            for prefix in [f"table{i}_" for i in range(1, 10)]:
                prefixed_name = f"{prefix}{expected.name}"
                actual = result.get(prefixed_name)
                if actual is not None:
                    matched_key, match_type = prefixed_name, "prefix"
                    break
                if actual is None and expected.aliases:
                    for alias in expected.aliases:
                        prefixed_alias = f"{prefix}{alias}"
                        actual = result.get(prefixed_alias)
                        if actual is not None:
                            matched_key, match_type = prefixed_alias, "prefix_alias"
                            break
                    if actual is not None:
                        break
        if actual is None:
            best_fuzzy_match = None
            best_fuzzy_score = 0.5
            for submitted_key in result:
                if submitted_key in matched_submitted_keys:
                    continue
                score = _compute_key_similarity(expected.name, submitted_key)
                if score > best_fuzzy_score:
                    best_fuzzy_score = score
                    best_fuzzy_match = submitted_key
            if best_fuzzy_match:
                actual = result[best_fuzzy_match]
                matched_key = best_fuzzy_match
                match_type = "fuzzy_high" if best_fuzzy_score >= 0.8 else "fuzzy_medium"

        matched_via[expected.name] = (matched_key, match_type)
        if matched_key:
            matched_submitted_keys.add(matched_key)
        comparison = _compare_result(expected, actual)
        details[expected.name] = comparison
        total_weight += expected.weight
        if comparison.within_tolerance:
            weighted_matches += expected.weight
        weighted_deviation += comparison.deviation * expected.weight

    # SECOND PASS: value-based matching for still-unmatched expected results
    unmatched_expected_names = [n for n, (mk, _) in matched_via.items() if mk is None]
    for expected_name in unmatched_expected_names:
        expected = next(e for e in expected_results if e.name == expected_name)
        if expected.alternatives or expected.value is None:
            continue
        for submitted_key in result:
            if submitted_key in matched_submitted_keys:
                continue
            submitted_value = result[submitted_key]
            try:
                if isinstance(submitted_value, str):
                    submitted_value = float(submitted_value)
                elif not isinstance(submitted_value, (int, float)):
                    continue
            except (ValueError, TypeError):
                continue
            if expected.value == 0:
                value_matches = submitted_value == 0
            elif expected.tolerance_type in (ToleranceType.PERCENTAGE, ToleranceType.RELATIVE):
                value_matches = abs(submitted_value - expected.value) / abs(expected.value) <= expected.tolerance
            else:
                value_matches = abs(submitted_value - expected.value) <= expected.tolerance
            if value_matches:
                matched_via[expected_name] = (submitted_key, "value_match")
                matched_submitted_keys.add(submitted_key)
                comparison = _compare_result(expected, submitted_value)
                details[expected_name] = comparison
                if comparison.within_tolerance:
                    weighted_matches += expected.weight
                weighted_deviation -= expected.weight
                weighted_deviation += comparison.deviation * expected.weight
                break

    all_submitted_keys = set(result.keys())
    unmatched_submitted_keys = sorted(all_submitted_keys - matched_submitted_keys)

    partial_score = weighted_matches / total_weight if total_weight > 0 else 0.0
    mean_deviation = weighted_deviation / total_weight if total_weight > 0 else 1.0
    return SuccessCheck(
        passed=partial_score >= PASS_THRESHOLD,
        partial_score=partial_score,
        mean_weighted_deviation=mean_deviation,
        details=details,
        unmatched_submitted_keys=unmatched_submitted_keys,
        matched_via=matched_via,
    )


def check_success(result: Any, profile: str = "best_of") -> SuccessCheck:
    """Score a submission against the expected results.

    ``profile`` selects the scoring regime (M7 §2.3, §4):
    - ``best_of`` (default, lenient): multi-path best-of — take the MAX partial_score
      across the primary AND the wider-tolerance ``ambiguous`` variant. Appropriate for
      the genuinely-ambiguous tier, but for confirmatory tiers it scores every run at the
      loosest bar (an audit showed it accepts e.g. a 2x error on sigma_omega).
    - ``primary_only`` (confirmatory/tight): score ONLY against the primary
      ``expected_results.json`` with its tight tolerances — no best-of over the loose
      variant. This is the regime a confirmatory single-vs-pipeline comparison needs.
    """
    variants = load_expected_variants()
    if profile == "primary_only":
        variants = {"expected_results": variants["expected_results"]}
    best: SuccessCheck | None = None
    best_variant: str | None = None
    evaluations: dict[str, dict[str, float]] = {}
    for variant, expected in variants.items():
        check = _check_success_against(expected, result)
        evaluations[variant] = {
            "partial_score": check.partial_score,
            "mean_weighted_deviation": check.mean_weighted_deviation,
        }
        if best is None:
            best, best_variant = check, variant
        elif check.partial_score > best.partial_score:
            best, best_variant = check, variant
        elif check.partial_score == best.partial_score and check.mean_weighted_deviation < best.mean_weighted_deviation:
            best, best_variant = check, variant
    assert best is not None
    best.selected_variant = best_variant
    best.variant_evaluations = evaluations
    return best


# --------------------------------------------------------------------------- #
# M6 plugin wrapper
# --------------------------------------------------------------------------- #


@dataclass
class NumericCompareEvaluator:
    evaluator_ref: str = "paper_replication.numeric_compare"
    kind: str = "plugin"
    scoring_profile: str = "best_of"  # "best_of" (lenient) | "primary_only" (confirmatory/tight)
    produces_headline_score: bool = True  # the runner's headline pass = this evaluator's `passed`

    def input_ref(self) -> EvaluatorInputRef:
        """Host-side provenance for the hidden reference (generic seam; runner stamps it)."""
        return reference_input_ref()

    def evaluate(self, *, payload: dict, commitment=None, input_ref: EvaluatorInputRef | None = None) -> RawEvaluation:
        check = check_success(payload, profile=self.scoring_profile)
        # Diagnostic split (M6 §4.1): the agent sees only structural flags; the
        # full per-result detail + selected variant stays researcher-side.
        missing = [n for n, (mk, _) in check.matched_via.items() if mk is None]
        return RawEvaluation(
            evaluator_ref=self.evaluator_ref,
            agent_feedback={
                "out_of_tolerance_flag": not check.passed,
                "missing_count": len(missing),
            },
            researcher_diagnostics={
                "passed": check.passed,
                "partial_score": check.partial_score,
                "mean_weighted_deviation": check.mean_weighted_deviation,
                "selected_variant": check.selected_variant,
                "variant_evaluations": check.variant_evaluations,
                "unmatched_submitted_keys": check.unmatched_submitted_keys,
                "matched_via": {k: list(v) for k, v in check.matched_via.items()},
                "details": {
                    k: {
                        "expected": c.expected, "actual": c.actual,
                        "within_tolerance": c.within_tolerance,
                        "deviation": c.deviation, "weight": c.weight,
                        "tolerance_type": c.tolerance_type.value, "tolerance": c.tolerance,
                    }
                    for k, c in check.details.items()
                },
            },
            determinism="deterministic",
        )
