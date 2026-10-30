"""Key normalization for result matching (faithful port from the OLD platform).

Verbatim port of `oaos/utils/key_normalization.py::KeyNormalizer` so the new
platform's `numeric_compare` matches submitted result keys against expected keys
**identically** to the calibrated old platform (abbreviation expansion,
tokenization, Jaccard fuzzy similarity). Porting this exactly is part of the
fidelity guarantee — the golden test (`tests/experiments`) locks it.
"""

from __future__ import annotations

import re


class KeyNormalizer:
    """Single source of truth for result key matching (ported verbatim)."""

    ABBREVIATION_MAP = {
        "col": "column",
        "tbl": "table",
        "pred": "predicted",
        "obs": "observations",
        "coef": "coefficient",
        "se": "standard_error",
        "std": "standard",
        "init": "initial",
        "r2": "r_squared",
        "rsq": "r_squared",
        "pval": "p_value",
        "pvalue": "p_value",
        "num": "number",
        "avg": "average",
        "mean": "average",
        "sd": "standard_deviation",
        "var": "variance",
        "cov": "covariance",
        "corr": "correlation",
        "est": "estimate",
        "err": "error",
        "win": "winner",
        "acc": "acceptance",
        "tax": "tax",
        "interact": "interaction",
        "x": "x",
    }

    @classmethod
    def normalize(cls, key: str) -> str:
        key = key.lower().replace("-", "_")
        parts = re.split(r"_+", key)
        expanded = []
        for part in parts:
            if not part:
                continue
            num_match = re.match(r"^([a-z]+)(\d+)$", part)
            if num_match:
                word_part = num_match.group(1)
                num_part = num_match.group(2)
                expanded_word = cls.ABBREVIATION_MAP.get(word_part, word_part)
                expanded.append(expanded_word)
                expanded.append(num_part)
            else:
                expanded.append(cls.ABBREVIATION_MAP.get(part, part))
        return "_".join(expanded)

    @classmethod
    def tokenize(cls, key: str) -> set[str]:
        parts = key.lower().split("_")
        tokens: set[str] = set()
        for part in parts:
            camel_parts = re.findall(r"[a-z]+|[A-Z][a-z]*", part)
            tokens.update(p.lower() for p in camel_parts)
            tokens.add(part)
        tokens.discard("")
        return tokens

    @classmethod
    def compute_similarity(cls, key1: str, key2: str) -> float:
        tokens1 = cls.tokenize(key1)
        tokens2 = cls.tokenize(key2)
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        return len(intersection) / len(union)

    @classmethod
    def keys_match(cls, key1: str, key2: str, threshold: float = 0.0) -> bool:
        if cls.normalize(key1) == cls.normalize(key2):
            return True
        if threshold > 0:
            return cls.compute_similarity(key1, key2) >= threshold
        return False


def extract_leading_number(s: object) -> float | None:
    """Extract a leading numeric value from strings like '0.250 (SE: 0.054)'.

    Ported from `oaos/utils/result_extraction.py::extract_leading_number`.
    """
    if not isinstance(s, str):
        return None
    match = re.match(r"^(-?\d+\.?\d*)", s.strip())
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None
