"""Capture file changes through host-backed workspaces.

capture_write records before/after hashes for host-mediated writes. Shared writes
use a lock keyed by the resolved path; this follows symbolic links but is not an
inode-based lock that unifies hard-link aliases. Locks cover one write rather
than serializing agents. Contention is recorded.

execute_with_capture scans one agent's private scratch before and after execution.
ArtifactVersion links captured versions to their producing events. Persistent
host files remain readable after container failure. See workspace/hashing.py
for scan filters and docker/capture.py for teardown copying."""

from __future__ import annotations

import asyncio
import difflib
import os
from contextlib import nullcontext
from pathlib import Path

from oaos2.kernel.run_dir import RunDir
from oaos2.trace.records import ArtifactVersion, FileChange
from oaos2.trace.retention import FileChangeFidelity, RetentionPolicy
from oaos2.trace.spine import RunSpine
from oaos2.ulid import new_ulid
from oaos2.workspace.acl import Zone
from oaos2.workspace.hashing import (
    FileState,
    LARGE_FILE_THRESHOLD,
    diff_scans,
    hash_bytes,
    is_binary,
    read_state,
    scan_tree,
)


def canonical_real_path(path: Path) -> str:
    """Resolve a path for use as a write-lock key.

    Relative components and symlinks resolve to one path. Distinct hard-link
    paths are not unified by inode identity."""
    return os.path.normcase(os.path.realpath(str(path)))


def _create_scratch_script(root: Path, path: Path, data: bytes) -> FileState:
    """Create a new script beneath a pinned directory without following links.

    Directory descriptors keep each traversal inside the host-owned mount root.
    Exclusive creation also refuses an existing ordinary file or hard link.
    """
    from oaos2.docker.isolation import IsolationViolation

    relative = path.relative_to(root)
    if not relative.parts or ".." in relative.parts:
        raise IsolationViolation("script path is outside its workspace")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(relative.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o644, dir_fd=directory)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            state = os.fstat(handle.fileno())
        return FileState(exists=True, hash=hash_bytes(data), size=len(data),
                         mtime=state.st_mtime,
                         data=data if len(data) <= LARGE_FILE_THRESHOLD and not is_binary(data) else None)
    except OSError as exc:
        raise IsolationViolation("script destination is not a new file inside scratch") from exc
    finally:
        os.close(directory)


class WorkspaceManager:
    def __init__(
        self,
        run_dir: RunDir,
        spine: RunSpine,
        retention: RetentionPolicy | None = None,
        artifact_zones: frozenset[str] = frozenset(),
        mode: str = "pilot",
        outcome_feeding_zones: frozenset[str] = frozenset(),
    ):
        self.run_dir = run_dir
        self.spine = spine
        self.retention = retention or RetentionPolicy()
        self.artifact_zones = artifact_zones
        # In confirmatory mode, writes into an outcome-feeding zone keep a FULL
        # patch regardless of the retention fidelity setting (M4 §2, §8 M3 floor):
        # the claim-bearing evidence must be fully reconstructable.
        self.mode = mode
        self.outcome_feeding_zones = outcome_feeding_zones
        self.file_locks: dict[str, asyncio.Lock] = {}
        self._holders: dict[str, str] = {}
        # realpath -> last captured operation, for the reconcile completeness
        # backstop (M4 §3, §6.5): a disk change with no matching capture is an
        # unexplained_change; a non-delete capture missing from disk is a phantom_write.
        self._captured: dict[str, str] = {}
        self._artifact_versions: dict[str, int] = {}
        self._artifact_last_id: dict[str, str] = {}
        self.patches_dir = run_dir.trace.parent / "filesystem" / "patches"
        self.patches_dir.mkdir(parents=True, exist_ok=True)

    # -- per-write capture -------------------------------------------------- #

    async def capture_write(
        self,
        *,
        agent_id: str,
        path: Path,
        new_bytes: bytes,
        zone: Zone,
        tool_call_event_id: str,
        turn_id: str | None = None,
        narration_ref: str | None = None,
        edit: bool = False,
        new_scratch_script: bool = False,
    ) -> FileChange:
        path = Path(path)
        if zone.is_shared:
            key = canonical_real_path(path)
            lock = self.file_locks.setdefault(key, asyncio.Lock())
            if lock.locked():  # someone else is mid-write on this exact file
                holder = self._holders.get(key)
                await self.spine.emit_event(
                    "file.write_contended",
                    agent_id=agent_id,
                    caused_by=tool_call_event_id,
                    payload={"path": str(path), "writers": [holder, agent_id]},
                )
            cm = lock
        else:
            cm = nullcontext()  # private scratch: lock-free, parallel-safe

        async with cm:
            if zone.is_shared:
                self._holders[canonical_real_path(path)] = agent_id
            if new_scratch_script:
                # Never inspect or open a pre-existing script path: it could be
                # a link or a pipe that blocks the host before validation.
                before = FileState(False, None, 0, 0.0, None)
                after = _create_scratch_script(self.run_dir.container_mount, path, new_bytes)
            else:
                before = read_state(path)
                if zone.is_shared:
                    await asyncio.sleep(0)  # model write duration; lets concurrent writers contend
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(new_bytes)
                after = read_state(path)

        op = "create" if not before.exists else "modify"
        self._captured[os.path.realpath(str(path))] = op
        patch_ref = self._maybe_store_patch(before, after, zone=zone)
        fc = FileChange(
            file_change_id=new_ulid(),
            agent_id=agent_id,
            path=str(path),
            zone=zone.name,
            zone_class=zone.zone_class,
            operation=op,
            hash_before=before.hash,
            hash_after=after.hash,
            patch_ref=patch_ref,
            cause_event_ids=[tool_call_event_id],
            narration_refs=[narration_ref] if narration_ref else [],
            turn_id=turn_id,
            enforcement=zone.enforcement,
            capture_source="tool",
        )
        await self._emit_filechange(fc, "file.edit" if edit else "file.write", tool_call_event_id)
        await self._maybe_version_artifact(fc, tool_call_event_id)
        return fc

    # -- scratch-scoped scan (execute side effects) ------------------------- #

    async def execute_with_capture(
        self,
        *,
        agent_id: str,
        scratch_root: Path,
        run_execute,  # awaitable callable performing the docker exec
        tool_call_event_id: str,
        zone: Zone,
        turn_id: str | None = None,
    ) -> list[FileChange]:
        pre = scan_tree(scratch_root)
        await run_execute()
        post = scan_tree(scratch_root, prior=pre)  # mtime+size pre-filter skips unchanged files
        out: list[FileChange] = []
        for ch in diff_scans(pre, post):
            fc = FileChange(
                file_change_id=new_ulid(),
                agent_id=agent_id,
                path=ch.path,
                zone=zone.name,
                zone_class=zone.zone_class,
                operation=ch.op,
                hash_before=ch.before,
                hash_after=ch.after,
                patch_ref=None,  # scan path captures hashes; patches need the bytes
                cause_event_ids=[tool_call_event_id],
                turn_id=turn_id,
                enforcement="os",
                capture_source="hash_scan",
            )
            self._captured[os.path.realpath(str(Path(scratch_root) / ch.path))] = ch.op
            event_class = "file.delete" if ch.op == "delete" else "file.write"
            await self._emit_filechange(fc, event_class, tool_call_event_id)
            await self._maybe_version_artifact(fc, tool_call_event_id)
            out.append(fc)
        return out

    async def capture_move(
        self, *, agent_id: str, src: Path, dst: Path, zone: Zone,
        tool_call_event_id: str, turn_id: str | None = None,
    ) -> FileChange:
        """Capture a tool-reported rename as a single ``file.moved``/``move`` event.

        A bare scan records a rename as delete+create (it cannot know they are the
        same file); ``file.moved`` is emitted only when a tool reports the rename
        explicitly (M4 §3 Moves), preserving the identity link.
        """
        src, dst = Path(src), Path(dst)
        before, after = read_state(src), read_state(dst)
        self._captured[os.path.realpath(str(src))] = "delete"
        self._captured[os.path.realpath(str(dst))] = "move"
        fc = FileChange(
            file_change_id=new_ulid(), agent_id=agent_id, path=str(dst), zone=zone.name,
            zone_class=zone.zone_class, operation="move",
            hash_before=before.hash, hash_after=after.hash, patch_ref=None,
            cause_event_ids=[tool_call_event_id], turn_id=turn_id,
            enforcement=zone.enforcement, capture_source="tool",
        )
        await self.spine.emit_event(
            "file.moved", agent_id=agent_id, turn_id=turn_id, caused_by=tool_call_event_id,
            payload={"file_change": fc.model_dump(), "moved_from": str(src)},
        )
        return fc

    def record_platform_write(self, path) -> None:
        """Mark a HOST-side platform write (a committed StateCommitment
        payload) as explained for :meth:`reconcile`. 2026-09-03 audit finding:
        every submission's ``submitted/`` payload flagged
        ``unexplained_change`` at teardown — 48 per dyad run of pure noise
        drowning the backstop's real signal. Only paths the caller can tie to
        an ACTUAL commitment belong here; strays in ``submitted/`` still
        flag."""
        self._captured[os.path.realpath(str(path))] = "platform_write"

    async def reconcile(self, roots: list[Path]) -> list[dict]:
        """Completeness backstop (M4 §3, §6.5): surface disagreement, never silently
        resolve. Scans ``roots`` and compares against everything captured this run.

        - A path present on disk that was never captured → ``unexplained_change``.
        - A captured non-delete path now absent from disk → ``phantom_write`` (a
          legitimately-captured delete is NOT a phantom — the ``op != delete`` guard).
        """
        on_disk: set[str] = set()
        for root in roots:
            root = Path(root)
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if p.is_file() or p.is_symlink():
                    on_disk.add(os.path.realpath(str(p)))
        mismatches: list[dict] = []
        for path in sorted(on_disk):
            if path not in self._captured:
                mismatches.append({"path": path, "cause": "unexplained_change"})
        for path, op in sorted(self._captured.items()):
            if op != "delete" and path not in on_disk:
                mismatches.append({"path": path, "cause": "phantom_write"})
        for m in mismatches:
            await self.spine.emit_event("file.reconciliation_mismatch", payload=m)
        return mismatches

    # -- helpers ------------------------------------------------------------ #

    def _maybe_store_patch(self, before, after, zone: Zone | None = None) -> str | None:
        # Confirmatory floor: an outcome-feeding zone keeps a full patch even when
        # retention is hashes_only (M4 §2, §8). Otherwise honor the retention setting.
        forced_full = (
            self.mode == "confirmatory"
            and zone is not None
            and zone.name in self.outcome_feeding_zones
        )
        if self.retention.file_changes is FileChangeFidelity.HASHES_ONLY and not forced_full:
            return None
        if after.data is None or before.data is None and before.exists:
            return None  # large/binary or absent bytes → hashes only
        before_text = (before.data or b"").decode("utf-8", errors="replace")
        after_text = (after.data or b"").decode("utf-8", errors="replace")
        if is_binary(after.data or b""):
            return None
        diff = "".join(
            difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
            )
        )
        ref = hash_bytes(diff.encode()).replace("sha256:", "")
        (self.patches_dir / f"{ref}.patch").write_text(diff)
        return f"filesystem/patches/{ref}.patch"

    async def _emit_filechange(self, fc: FileChange, event_class: str, caused_by: str) -> None:
        await self.spine.emit_event(
            event_class,
            agent_id=fc.agent_id,
            turn_id=fc.turn_id,
            caused_by=caused_by,
            payload={"file_change": fc.model_dump()},
        )

    async def _maybe_version_artifact(self, fc: FileChange, caused_by: str) -> None:
        if fc.zone not in self.artifact_zones or fc.operation == "delete":
            return
        artifact_id = fc.path
        version = self._artifact_versions.get(artifact_id, 0) + 1
        self._artifact_versions[artifact_id] = version
        av = ArtifactVersion(
            artifact_version_id=new_ulid(),
            artifact_id=artifact_id,
            version=version,
            file_change_id=fc.file_change_id,
            content_hash=fc.hash_after or "",
        )
        fc.artifact_version_id = av.artifact_version_id
        prior = self._artifact_last_id.get(artifact_id)
        self._artifact_last_id[artifact_id] = av.artifact_version_id
        await self.spine.emit_event(
            "artifact.versioned",
            agent_id=fc.agent_id,
            turn_id=fc.turn_id,
            caused_by=caused_by,
            payload={"artifact_version": av.model_dump(), "supersedes": prior},
        )
