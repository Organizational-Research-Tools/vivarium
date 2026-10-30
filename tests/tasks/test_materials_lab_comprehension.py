"""Offline checks of survey spending and evidence identity; no provider calls."""

import asyncio
import json
import gzip
from types import SimpleNamespace

import pytest

from oaos2.models.types import ModelResponse, NeutralBlock, TokenSplit
from scripts import materials_lab_comprehension as survey


class SurveyAdapter:
    def __init__(self):
        self.calls = 0

    def estimate_tokens(self, messages, tools):
        return 0

    def translate(self, req):
        return req

    async def invoke(self, req):
        self.calls += 1
        await asyncio.sleep(0)  # both labs attempt admission before either settles
        return req

    def normalize(self, raw, req, raw_ref):
        return ModelResponse(req.call_id, req.model_ref, "end_turn",
                             [NeutralBlock(kind="text", text="answer")],
                             TokenSplit(output=20000))


def _opening(model="anthropic/claude-sonnet-4-6"):
    return {"system": "system", "user": "opening", "lab_info": "info", "tools": [],
            "model_ref": model, "sampling": {"max_output_tokens": 20000, "temperature": 1.0},
            "reasoning": {"kind": "thinking", "budget_tokens": 8000}}


def _args(cap=1.0):
    return SimpleNamespace(cap=cap, stage_questions={}, candidate=None, seed=9,
                           level="approved_list", tools_from=None)


@pytest.mark.asyncio
async def test_concurrent_survey_calls_reserve_the_shared_cap(monkeypatch):
    adapter = SurveyAdapter()
    monkeypatch.setattr("oaos2.experiments.runner._adapter_for", lambda *a, **kw: adapter)
    result = await survey.main_async(_args(0.35), {("preset", lab): _opening() for lab in ("a", "b")})
    assert result["estimated_usd"] <= 0.35
    assert adapter.calls == 1
    assert result["complete"] is False
    assert len(result["labs"]) == 2  # a denied lab stays in the denominator


@pytest.mark.asyncio
async def test_survey_evidence_identifies_and_prices_the_actual_model(monkeypatch):
    adapter = SurveyAdapter()
    monkeypatch.setattr("oaos2.experiments.runner._adapter_for", lambda *a, **kw: adapter)
    o = _opening("anthropic/claude-haiku-4-5")
    result = await survey.main_async(_args(), {("preset", "a"): o})
    assert result["estimated_usd"] == pytest.approx(0.1)
    assert result["shown"]["preset"]["a"]["model_ref"] == o["model_ref"]
    assert result["shown"]["preset"]["a"]["reasoning"] == o["reasoning"]
    assert result["pricing_hash"]
    assert result["labs"][0]["calls"][0]["request"]["model_ref"] == o["model_ref"]
    json.dumps(result)  # evidence must remain serializable with full request and usage records


@pytest.mark.asyncio
async def test_failed_survey_call_keeps_partial_answers_and_unsettled_cost(monkeypatch):
    class FailingAdapter(SurveyAdapter):
        async def invoke(self, req):
            self.calls += 1
            if self.calls == 3:
                raise RuntimeError("provider response lost")
            return req

    adapter = FailingAdapter()
    monkeypatch.setattr("oaos2.experiments.runner._adapter_for", lambda *a, **kw: adapter)
    args = _args(2.0)
    args.stage_questions = {"first": "question", "second": "question"}
    result = await survey.main_async(args, {("preset", "a"): _opening()})
    assert result["complete"] is False
    assert result["labs"][0]["answers"]["first"]["answer"] == "answer"
    assert result["reserved_usd"] == pytest.approx(0.3)
    assert result["unsettled_calls"]
    assert "provider response lost" in result["labs"][0]["error"]


@pytest.mark.parametrize("cap", [0, -1, float("nan"), float("inf")])
@pytest.mark.asyncio
async def test_invalid_survey_cap_refuses_before_adapter_creation(monkeypatch, cap):
    def forbidden(*args, **kwargs):
        pytest.fail("adapter must not be created")
    monkeypatch.setattr("oaos2.experiments.runner._adapter_for", forbidden)
    with pytest.raises(ValueError, match="positive finite"):
        await survey.main_async(_args(cap), {("preset", "a"): _opening()})


@pytest.mark.parametrize("options", [
    ["--model", "anthropic/claude-haiku-4-5", "--tools-from", "unused"],
    ["--go"],
])
def test_invalid_launch_options_fail_before_building_openings(monkeypatch, options):
    monkeypatch.setattr("sys.argv", ["survey", *options])
    monkeypatch.setattr(survey, "openings", lambda args: pytest.fail("must refuse first"))
    with pytest.raises(SystemExit) as exc:
        survey.main()
    assert exc.value.code == 2


def test_survey_does_not_overwrite_existing_evidence(monkeypatch, tmp_path):
    out = tmp_path / "evidence.json"
    out.write_text("original evidence")
    monkeypatch.setattr("sys.argv", ["survey", "--go", "--out", str(out)])
    monkeypatch.setattr(survey, "openings", lambda args: pytest.fail("must refuse first"))
    with pytest.raises(SystemExit) as exc:
        survey.main()
    assert exc.value.code == 2
    assert out.read_text() == "original evidence"


def test_regulator_questions_match_the_current_rule_and_preserve_old_probes():
    o = {"question_form": "regulator-v1", "variant": "variant KB4", "my_records": "before the agreement (raw text)"}
    for key, template in survey.QUESTIONS.items():
        if key.startswith(("R_", "S_")):
            rendered = survey.question_text(template, o)
            assert "laboratories agreed" not in rendered and "laboratories have agreed" not in rendered
            assert "before the agreement" not in rendered.replace(o["my_records"], "")
            legacy = survey.question_text(template, {**o, "question_form": "agreement-v1"})
            assert legacy == template.replace("{variant}", o["variant"]).replace("{my_records}", o["my_records"])
    assert survey.question_text(survey.QUESTIONS["R_restate"], o).endswith("what rule applies to the supplier variants?")
    assert o["my_records"] in survey.question_text(survey.QUESTIONS["R_listing"], o)


def test_current_supplier_opening_selects_the_regulator_question_form():
    o = survey.opening("materials_divisible_supplier", "lab_a", 9, "approved_list", None)
    assert o["question_form"] == "regulator-v1"
    assert "Packaging Materials Agency" in o["lab_info"]


@pytest.mark.parametrize("level", ["approved_list", "licence", "injury"])
def test_the_testing_firms_are_asked_in_their_own_words_at_every_reason(level):
    """supplier-k (October 11, 2026): the survey shows a firm what a run shows it and asks the regulator's questions
    in the firms' words; none of the old words reaches it, in the opening, the tools or the questions."""
    from oaos2.tasks.plugins.materials_lab.vocabulary import OLD_WORDS
    o = survey.opening("pc1_testing_competitive", "firm_d", 9, level, None,
                       model_ref="anthropic/claude-haiku-5-5", effort="medium")
    assert o["question_form"] == "testing-v1" and o["variant"].startswith("supplier variant ")
    assert "Packaging Materials Agency" in o["lab_info"] and "firm_info" in {t.name for t in o["tools"]}
    shown = [o["system"], o["user"], o["lab_info"], o["my_records"] or ""]
    shown += [t.name + t.description + str(t.parameters_schema) for t in o["tools"]]
    shown += [survey.question_text(q, o) for k, q in survey.QUESTIONS.items() if k.startswith(("R_", "S_"))]
    for text in shown:
        assert not OLD_WORDS.search(text), OLD_WORDS.search(text)
    assert "[board #1" in o["user"] and "program office:" in o["user"]  # the open topic, by the runtime's own name


def test_stored_effort_model_recovers_its_recorded_setting(tmp_path):
    (tmp_path / "trace").mkdir()
    (tmp_path / "raw").mkdir()
    (tmp_path / "trace/events.jsonl").write_text(json.dumps({"event_class": "model.invoked", "agent_id": "lab_a",
        "payload": {"raw_provider_request_ref": "raw/request1"}}) + "\n")
    (tmp_path / "manifest.json").write_text(json.dumps({"extensions": {"role_reasoning": {"lab_a": {"effort": "medium"}}}}))
    with gzip.open(tmp_path / "raw/request1.json.gz", "wt") as stream:
        json.dump({"request": {"model_ref": "anthropic/claude-haiku-5-5",
                              "reasoning": {"kind": "thinking", "budget_tokens": None}}}, stream)
    assert survey.stored_first_request(tmp_path, "lab_a")["reasoning"]["effort"] == "medium"
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="no recorded effort"):
        survey.stored_first_request(tmp_path, "lab_a")


@pytest.mark.asyncio
async def test_rejected_survey_request_releases_its_reservation(monkeypatch):
    from oaos2.models.adapters.base import ProviderError

    class RejectingAdapter(SurveyAdapter):
        async def invoke(self, req):
            raise ProviderError("context too long", not_billed=True)

    monkeypatch.setattr("oaos2.experiments.runner._adapter_for", lambda *a, **kw: RejectingAdapter())
    result = await survey.main_async(_args(), {("preset", "a"): _opening()})
    assert not result["complete"] and not result["unsettled_calls"] and result["reserved_usd"] == 0
    assert result["labs"][0]["calls"][0]["usage_status"] == "not_billed"
