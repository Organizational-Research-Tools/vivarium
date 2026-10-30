"""The offline suite never reaches a provider or Docker (tests/conftest.py; consolidation step E).

A test file whose import or skip condition asks the Docker daemon whether it is there, or reads
provider credentials, must be one of the live files the conftest leaves out of collection.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from tests.conftest import LIVE_TEST_FILES, collect_ignore

TESTS = Path(__file__).resolve().parent
# asking the daemon, or reading a provider key from the environment or .env (key names alone are fine)
_LIVE = re.compile(r"""LocalDockerBackend\.available\(\)|environ\.get\(["'][A-Z_]*API_KEY|load_dotenv\(""")


def test_live_files_are_left_out_unless_opted_in():
    if os.environ.get("OAOS2_LIVE") != "1":
        assert sorted(collect_ignore) == sorted(LIVE_TEST_FILES)


def test_every_file_that_reaches_outside_is_a_live_file():
    reaching = sorted(p.relative_to(TESTS).as_posix() for p in TESTS.rglob("test_*.py")
                      if p.name != Path(__file__).name and _LIVE.search(p.read_text(errors="replace")))
    assert set(reaching) <= set(LIVE_TEST_FILES), sorted(set(reaching) - set(LIVE_TEST_FILES))
