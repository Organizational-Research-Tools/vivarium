"""Read submission bytes only when the saved commitment certifies their identity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class SubmissionIntegrityError(ValueError):
    """A submitted file is missing, changed, ambiguous, or was never committed."""


def read_verified_submissions(run_root: Path | str, *, events=None) -> dict[str, dict]:
    """Return committed JSON payloads after checking every recorded content hash.

    Captured files take precedence over the active container mount and the legacy
    submitted directory. The trace names the allowed set; an extra JSON file cannot
    add evidence to scoring. A damaged capture never falls back to another copy.
    """
    from oaos2.trace.invariants import load_all_events

    root = Path(run_root)
    stream = load_all_events(root) if events is None else events
    commitments = {}
    for event in stream:
        if event.get("event_class") != "state.committed":
            continue
        sc = (event.get("payload") or {}).get("state_commitment") or {}
        cid = sc.get("commitment_id")
        if not isinstance(cid, str) or not cid or Path(cid).name != cid or cid in (".", ".."):
            raise SubmissionIntegrityError("invalid commitment identifier")
        if cid in commitments:
            raise SubmissionIntegrityError(f"duplicate commitment {cid!r}")
        if sc.get("payload_ref") != f"submitted/{cid}.json":
            raise SubmissionIntegrityError(f"unexpected payload reference for {cid!r}")
        commitments[cid] = sc
    source = next((p for p in (root / "captured" / "submitted",
                              root / "container_mount" / "submitted", root / "submitted")
                   if p.exists() or p.is_symlink()), None)
    if source is not None and (source.is_symlink() or not source.is_dir()):
        raise SubmissionIntegrityError("submission source must be a regular directory")
    files = {p.stem: p for p in source.glob("*.json")} if source else {}
    if set(files) != set(commitments):
        raise SubmissionIntegrityError(
            f"submission set differs from commitments: missing={sorted(set(commitments)-set(files))}, "
            f"uncommitted={sorted(set(files)-set(commitments))}")
    result = {}
    for cid, sc in sorted(commitments.items()):
        path = files[cid]
        if path.is_symlink() or not path.is_file():
            raise SubmissionIntegrityError(f"submission {cid!r} must be a regular file")
        raw = path.read_bytes()
        if "sha256:" + hashlib.sha256(raw).hexdigest() != sc.get("content_hash"):
            raise SubmissionIntegrityError(f"submission {cid!r} content hash mismatch")
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise SubmissionIntegrityError(f"submission {cid!r} is invalid JSON") from exc
        if not isinstance(value, dict):
            raise SubmissionIntegrityError(f"submission {cid!r} must be a JSON object")
        result[cid] = value
    return result
