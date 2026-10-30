"""Pre-dispatch cap is a VALIDATED bound, not asserted (M3 §3.2, §22).

Across a corpus, estimate_tokens must never under-count the provider-reported input;
any undercount fails the gate and the margin must widen until clean.
"""

from __future__ import annotations

from oaos2.experiments.parity import (
    CorpusEntry,
    EstimateValidationReport,
    estimate_corpus_from_archive,
    run_conformance_trace,
    validate_estimate_corpus,
)
from oaos2.models.adapters.stub import StubProviderAdapter
from oaos2.models.types import BlockKind, NeutralBlock, NeutralMessage, ToolSpec


class _UnderCountAdapter:
    """An adapter whose estimate deliberately under-counts — must fail the gate."""

    def estimate_tokens(self, messages, tools):
        return 10  # always too low


def _entry(text: str, actual: int) -> CorpusEntry:
    return CorpusEntry(
        messages=[NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text=text)])],
        tools=[ToolSpec(name="t", description="d", parameters_schema={})],
        reported_input_tokens=actual, call_id="c",
    )


def test_clean_corpus_passes() -> None:
    # The stub never under-counts (margin + floor over the exact base).
    corpus = [_entry("x" * n, actual=5) for n in (10, 100, 500)]
    report = validate_estimate_corpus(StubProviderAdapter(), corpus)
    assert isinstance(report, EstimateValidationReport)
    assert report.clean and not report.undercounts and report.n == 3
    assert report.worst_ratio >= 1.0 and report.suggested_margin_multiplier == 1.0


def test_undercount_fails_and_suggests_margin() -> None:
    # actual 100, estimate fixed at 10 → worst ratio 0.1 → need ~10x margin.
    corpus = [_entry("anything", actual=100)]
    report = validate_estimate_corpus(_UnderCountAdapter(), corpus)
    assert not report.clean and len(report.undercounts) == 1
    assert report.undercounts[0]["shortfall"] == 90
    assert round(report.suggested_margin_multiplier, 2) == 10.0


async def test_corpus_reconstructed_from_archive_is_clean(tmp_path) -> None:
    # Drive real model.invoked/model.responded events (requests captured in raw/) through
    # the gateway, then reconstruct the corpus from the archive and validate the bound.
    adapter = StubProviderAdapter()
    await run_conformance_trace(adapter, tmp_path, model_ref="stub/deterministic")
    corpus = estimate_corpus_from_archive(tmp_path)
    assert corpus, "expected at least one model call reconstructed from the archive"
    report = validate_estimate_corpus(adapter, corpus)
    assert report.clean, f"stub must never under-count, worst_ratio={report.worst_ratio}"
    # Reconstruction preserved the request shape (non-empty messages on each entry).
    assert all(e.messages for e in corpus)
