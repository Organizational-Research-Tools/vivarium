"""Content hashing + patch fidelity (M4 §2, §3, §7).

A fast content hash with a concrete large/binary threshold above which
``patch_ref`` is null regardless of retention (M4 §7.2), plus mtime+size-filtered
tree scanning for the scratch-scoped side-effect capture (M4 §3).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

LARGE_FILE_THRESHOLD = 1_048_576  # 1 MiB; above this → hashes only (patch_ref null)


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


@dataclass
class FileState:
    exists: bool
    hash: str | None
    size: int
    mtime: float
    data: bytes | None  # None if large/binary (not held in memory)


def read_state(path: Path, *, load_bytes: bool = True) -> FileState:
    p = Path(path)
    if not p.exists() or p.is_dir():
        return FileState(exists=False, hash=None, size=0, mtime=0.0, data=None)
    if p.is_symlink():
        # Captured as a 0-byte special with target recorded (M4 §7.4); never followed.
        target = str(p.readlink()).encode()
        return FileState(exists=True, hash=hash_bytes(b"symlink:" + target), size=0,
                         mtime=p.lstat().st_mtime, data=None)
    stat = p.stat()
    data = p.read_bytes()
    keep = load_bytes and stat.st_size <= LARGE_FILE_THRESHOLD and not is_binary(data)
    return FileState(
        exists=True, hash=hash_bytes(data), size=stat.st_size, mtime=stat.st_mtime,
        data=data if keep else None,
    )


@dataclass
class ScanEntry:
    path: str
    hash: str
    size: int
    mtime: float


def scan_tree(root: Path, prior: dict[str, "ScanEntry"] | None = None) -> dict[str, ScanEntry]:
    """Scan a tree in sorted path order (determinism); hash regular files (M4 §3).

    ``prior`` enables the mtime+size pre-filter: a file whose ``(size, mtime)``
    is unchanged from the prior scan reuses the prior hash instead of being
    re-read and re-hashed — the §6 "scan cost on large tree" mitigation. Hashing
    is still the source of truth for *change detection*; the pre-filter only
    avoids redundant reads of provably-unchanged files.
    """
    root = Path(root)
    out: dict[str, ScanEntry] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        rel = str(p.relative_to(root))
        if prior is not None and not p.is_symlink():
            try:
                st = p.stat()
                prev = prior.get(rel)
                if prev is not None and prev.size == st.st_size and prev.mtime == st.st_mtime:
                    out[rel] = ScanEntry(path=rel, hash=prev.hash, size=prev.size, mtime=prev.mtime)
                    continue
            except OSError:
                pass
        fs = read_state(p, load_bytes=False)
        out[rel] = ScanEntry(path=rel, hash=fs.hash or "", size=fs.size, mtime=fs.mtime)
    return out


@dataclass
class ScanDiff:
    path: str
    op: str  # create | modify | delete
    before: str | None
    after: str | None


def diff_scans(pre: dict[str, ScanEntry], post: dict[str, ScanEntry]) -> list[ScanDiff]:
    """Diff two scans (mtime+size pre-filter skips unchanged; sorted for determinism)."""
    diffs: list[ScanDiff] = []
    for path in sorted(set(pre) | set(post)):
        a, b = pre.get(path), post.get(path)
        if a is None and b is not None:
            diffs.append(ScanDiff(path, "create", None, b.hash))
        elif a is not None and b is None:
            diffs.append(ScanDiff(path, "delete", a.hash, None))
        elif a is not None and b is not None:
            if a.hash != b.hash:  # mtime/size pre-filter is implicit in the hash compare here
                diffs.append(ScanDiff(path, "modify", a.hash, b.hash))
    return diffs
