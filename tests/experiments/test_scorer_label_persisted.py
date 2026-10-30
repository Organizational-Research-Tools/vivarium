"""The headline scorer's own label for its verdict (the materials lab splits honest from
violating credits) is kept in the score and written to run_status.json as
``scorer_label``, apart from ``label``, which is the run's assisted/unassisted setting."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from oaos2.experiments.runner import _persist_run_status, _score
from oaos2.tasks.loader import load_task_pack


class _Spine:
    async def emit_event(self, *args, **kwargs):
        return "e"


def _coordinator(pack, payload):
    contract = pack.outcome_contract
    commitment = next(c for c in contract.commitments if "materials_lab.credit_score" in c.evaluators)
    return SimpleNamespace(contract=contract, payloads={commitment.commitment_id: payload},
                           committed_event_ids={})


def test_headline_label_reaches_the_score_and_the_status_file(tmp_path) -> None:
    pack = load_task_pack("materials_lab", profile="six_institution")
    payload = {"credits": 2, "projects": 9, "honest_credits": 1, "credited_violations": 1}
    score = asyncio.run(_score(pack, _coordinator(pack, payload), _Spine()))
    assert score["passed"] is True and score["headline_label"] == "honest and violating credits"
    cell = SimpleNamespace(preset_id="p", model_ref="m", passed=True, partial_score=score["partial_score"],
                           scored=True, label="unassisted", closed=True, archive_valid=True, cost_usd=0.0,
                           exposure_confounded=False, score_detail=score)
    _persist_run_status(tmp_path, cell)
    status = json.loads((tmp_path / "run_status.json").read_text())
    assert status["scorer_label"] == "honest and violating credits" and status["label"] == "unassisted"
    # a run whose score has no headline label writes None, not a stale value
    _persist_run_status(tmp_path, SimpleNamespace(**{**vars(cell), "score_detail": {}}))
    assert json.loads((tmp_path / "run_status.json").read_text())["scorer_label"] is None
