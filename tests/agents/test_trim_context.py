"""The context trim applied after a refused call (G5, October 15, 2026): reasoning dropped, long
tool outputs and messages from others outside the last few messages shortened to a note, the most
recent messages untouched. Nothing here is a model."""

from __future__ import annotations

from oaos2.agents.model_agent import INBOX_HEAD, TRIM_KEEP_RECENT, _trim_context
from oaos2.models.types import BlockKind, NeutralBlock, NeutralMessage


def _text(role, text):
    return NeutralMessage(role, [NeutralBlock(kind=BlockKind.TEXT.value, text=text)])


def test_older_messages_from_others_are_shortened_and_recent_ones_kept() -> None:
    long = "x" * 2000
    msgs = [_text("system", "rules"), _text("user", "opening"),
            _text("user", f"{INBOX_HEAD}\n[board #1] heat_team: {long}"),
            _text("assistant", "noted"),
            _text("user", f"{INBOX_HEAD}\nshort"),
            *[_text("assistant" if i % 2 else "user", f"{INBOX_HEAD}\n[board #{i}] {long}" if i % 2 == 0 else "ok")
              for i in range(TRIM_KEEP_RECENT)]]
    _trim_context(msgs)
    old = msgs[2].blocks[0].text
    assert old.startswith(INBOX_HEAD) and "earlier messages from others omitted" in old and len(old) < 200
    assert msgs[1].blocks[0].text == "opening" and msgs[4].blocks[0].text.endswith("short")   # short ones stay
    recent = [m.blocks[0].text for m in msgs[-TRIM_KEEP_RECENT:] if m.role == "user"]
    assert recent and all(len(t) > 2000 for t in recent)   # the last messages are untouched



def test_the_platforms_own_notices_survive_the_trim() -> None:
    long = "y" * 1500
    block = (f"{INBOX_HEAD}\n[board #3] heat_team: {long}\n[workshop] The client did not accept the delivery of "
             f"project A1 (report rep_X); rejected deliveries of A1: 1 of 2.\n[note from water_team] {long}\n"
             "[client] Trial delivery of p_Y (project A1): accepted by the client's acceptance testing.")
    msgs = [_text("system", "rules"), _text("user", "opening"), _text("user", block),
            *[_text("assistant" if i % 2 else "user", "ok") for i in range(TRIM_KEEP_RECENT)]]
    _trim_context(msgs)
    out = msgs[2].blocks[0].text
    assert "[workshop] The client did not accept" in out and "[client] Trial delivery" in out
    assert "[board #3]" not in out and "[note from water_team]" not in out and "omitted" in out


def test_inbox_shortening_is_a_stable_fallback() -> None:
    """October 18, 2026: when summarizing and evicting cannot reach the budget, long incoming
    messages outside the recent ones are shortened once; a second pass changes nothing (stable for
    the provider cache), and the recent messages and the opening two are untouched."""
    from oaos2.agents.model_agent import INBOX_SHORTEN_CHARS, _shorten_inbox
    long = "r" * (INBOX_SHORTEN_CHARS + 500)
    msgs = [_text("system", "rules"), _text("user", long), _text("user", long), _text("assistant", long),
            _text("user", long), _text("user", long), _text("user", long)]
    assert _shorten_inbox(msgs, 2) == 2          # messages 2 and 4: user, outside the opening and the last 2
    snapshot = [m.blocks[0].text for m in msgs]
    assert _shorten_inbox(msgs, 2) == 0 and [m.blocks[0].text for m in msgs] == snapshot
    assert msgs[1].blocks[0].text == long and msgs[3].blocks[0].text == long        # opening, assistant
    assert msgs[-1].blocks[0].text == long and msgs[-2].blocks[0].text == long      # the recent ones

# The trim running once per refusal episode is tested through the agent loop, by the requests the
# model receives: tests/tasks/test_context_repair_loop.py (lineage audit F06, October 19, 2026).
