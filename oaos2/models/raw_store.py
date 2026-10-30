"""Store provider response dictionaries by content hash under raw/.

put serializes the dictionary with sorted JSON keys, hashes it, and writes a
compressed <hash>.json.gz file if absent. It returns raw/<hash>; get reads the
same dictionary. This preserves returned data, not original HTTP response bytes.
The store has no sampling or retention-policy logic: callers decide whether to
invoke it. Gzip file bytes include compression metadata and are not promised
byte-identical across independent writes."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


class RawPayloadStore:
    def __init__(self, run_dir: Path):
        self.raw_dir = Path(run_dir) / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def put(self, payload: dict) -> str:
        """Store a payload content-addressed; return its ``raw/<hash>`` ref (dedup)."""
        blob = json.dumps(payload, sort_keys=True).encode()
        digest = hashlib.sha256(blob).hexdigest()
        path = self.raw_dir / f"{digest}.json.gz"
        if not path.exists():  # dedup: identical payloads stored once
            with gzip.open(path, "wb") as f:
                f.write(blob)
        return f"raw/{digest}"

    def get(self, ref: str) -> dict:
        digest = ref.split("/", 1)[1]
        path = self.raw_dir / f"{digest}.json.gz"
        with gzip.open(path, "rb") as f:
            return json.loads(f.read())
