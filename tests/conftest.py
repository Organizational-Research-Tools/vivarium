"""Keep the offline suite offline.

Three test files can reach outside the machine: the Anthropic adapter test makes paid calls when a
key is present, and the two live Docker tests launch real containers when a daemon answers. Their
skip conditions run while pytest collects them, so even a skipped run read credentials or asked the
Docker daemon whether it was there. They are left out of collection unless the environment sets
``OAOS2_LIVE=1``, which a person sets only for a run they mean to pay for. ``python -m pytest tests/``
therefore never contacts a provider or Docker.
"""

import os

LIVE_TEST_FILES = (
    "models/test_anthropic_adapter.py",
    "docker/test_live_docker.py",
    "docker/test_python_bug_repair_live.py",
)

collect_ignore = [] if os.environ.get("OAOS2_LIVE") == "1" else list(LIVE_TEST_FILES)


# Public release: the development studies' presets are test fixtures (tests/fixtures/organizations/).
import os as _os
from pathlib import Path as _Path

_os.environ.setdefault("OAOS2_ORGANIZATIONS", str(_Path(__file__).parent / "fixtures" / "organizations"))

# Public release: tests listed in released_exclusions.txt are deselected. They use records, scripts or
# the earlier tasks' materials (as fixtures) that this release does not carry; the file gives each reason.
_EXCLUDED = {line.split("#", 1)[0].strip()
             for line in (_Path(__file__).parent / "released_exclusions.txt").read_text().splitlines()} - {""}


def pytest_collection_modifyitems(config, items):
    dropped = [item for item in items if item.nodeid in _EXCLUDED]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = [item for item in items if item.nodeid not in _EXCLUDED]
