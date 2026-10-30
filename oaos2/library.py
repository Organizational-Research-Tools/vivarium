"""Config-library location (the declarative experiment data, outside the engine).

Configurations — task pack manifests + assets, organization specs, experiment
designs — live as **data** in a committed ``library/`` directory, symmetric with
the ``runs/`` output directory and separate from the ``oaos2/`` engine code. A
config-building tool writes files here; the platform's loaders read them.

``OAOS2_LIBRARY`` overrides the location (e.g. to point at an external library).
"""

from __future__ import annotations

import os
from pathlib import Path


def library_dir() -> Path:
    env = os.environ.get("OAOS2_LIBRARY")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "library"  # repo/library


LIBRARY_DIR = library_dir()
