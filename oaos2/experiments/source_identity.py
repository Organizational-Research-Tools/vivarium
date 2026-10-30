"""Fingerprint executable repository sources independently of Git and study pins.

A launch-pin file can record this value before it is committed: standalone documentation,
preregistrations, evidence, and Git metadata do not contribute to the fingerprint.
Task materials and experiment settings have their own hashes in the research setup.
Python files are hashed as bytes, including comments, docstrings, and embedded text.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


_SOURCE_TREES = ("oaos2", "scripts", "library/tasks")
# Python dependency tools use these conventional root-level lockfile names.
_LOCKFILES = ("uv.lock", "poetry.lock", "pdm.lock", "Pipfile.lock", "requirements.lock")


def source_code_sha256(root: Path | str) -> str:
    """Hash sorted relative paths and exact bytes, without modifying the repository.

    Includes Python sources in the platform, scripts, and task packages, plus
    pyproject.toml and any declared lockfile that exists. Missing optional files
    contribute nothing; adding, removing, or renaming a source changes the hash.
    File timestamps, standalone documentation, and launch/evidence pins do not affect it.
    A comment or docstring edit in an included Python file does affect it.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"source root is not a directory: {root}")
    files = {path for tree in _SOURCE_TREES for path in (root / tree).rglob("*.py")
             if path.is_file()}
    files.update(root / name for name in ("pyproject.toml", *_LOCKFILES)
                 if (root / name).is_file())
    digest = hashlib.sha256(b"oaos2-source-code-v1\0")
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        name = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        # Length framing distinguishes path/content boundaries even for unusual
        # filenames and binary bytes in a nominal Python source file.
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()
