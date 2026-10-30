"""Recipient names written as a JSON string or in quotes (October 12, 2026): the agents sometimes pass
`'["lab_a"]'` or `'"firm_c"'` as `to_roles`; the note and the grants reach the named agent instead of being
refused for an agent named with its quotes."""

import pytest

from oaos2.communication.board import recipient_names


@pytest.mark.parametrize("raw,names", [
    (["firm_a", "firm_b"], ["firm_a", "firm_b"]),
    ("firm_a, firm_b", ["firm_a", "firm_b"]),
    ('["lab_a"]', ["lab_a"]),
    ('["lab_a", "lab_c"]', ["lab_a", "lab_c"]),
    ('"firm_c"', ["firm_c"]),
    ('["lab_b"', ["lab_b"]),
    (['"firm_b"', "firm_b"], ["firm_b"]),
    ("", []),
    (None, []),
])
def test_recipient_names(raw, names):
    assert recipient_names(raw) == names


def test_an_unknown_name_is_still_an_unknown_name():
    assert recipient_names('"firm_z"') == ["firm_z"]  # the refusal then names firm_z, not '"firm_z"'
