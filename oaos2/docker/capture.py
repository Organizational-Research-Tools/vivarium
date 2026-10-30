"""Copy host-backed artifacts without following symbolic links.

Capture can read these files after a container has stopped because they live
on the host. Symlinks are copied as links, not followed into their targets.
The runner separately checks for path escapes before copying and removes a
container only after successful capture. Temporary container files are outside
this host-directory copy."""

from __future__ import annotations

import fnmatch
import os
import shutil
from pathlib import Path


def copy_artifacts(src_root: Path, dst_root: Path, globs: list[str]) -> list[str]:
    """Copy matching files from ``src_root`` to ``dst_root`` WITHOUT following symlinks.

    Returns the list of captured relative paths. Directories are recreated;
    regular files are copied; symlinks are recreated as symlinks (never resolved),
    so nothing outside the sandbox is dereferenced.
    """
    src_root = Path(src_root)
    dst_root = Path(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)
    captured: list[str] = []

    for path in sorted(src_root.rglob("*")):
        rel = path.relative_to(src_root)
        if not _matches(str(rel), globs):
            continue
        target = dst_root / rel
        if path.is_symlink():
            # Recreate the symlink verbatim — DO NOT follow it (the control).
            target.parent.mkdir(parents=True, exist_ok=True)
            link_target = os.readlink(path)
            if target.exists() or target.is_symlink():
                target.unlink()
            os.symlink(link_target, target)
            captured.append(str(rel))
        elif path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target, follow_symlinks=False)
            captured.append(str(rel))
    return captured


def _matches(rel_path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, g) or g == "**/*" for g in globs)
