"""ULID generation (M1 §3.2): producer-assigned, lexicographically sortable IDs.

A ULID is a 128-bit identifier: a 48-bit millisecond timestamp followed by 80
bits of randomness, rendered as 26 Crockford-Base32 characters. Two properties
the trace spine relies on (DESIGN §6.2, M1 §3.2):

- **Sortable by creation time.** The leading timestamp makes the canonical
  string ordering agree with wall-clock creation order. (This is convenience for
  humans/queries; it is *not* the trace's total order — that is the
  writer-assigned ``sequence_number``. Ordering events by ULID would be a bug,
  exactly as ordering by ``timestamp`` is, M1 §2.)
- **Producer-assignable without coordination.** A producer mints the id locally
  and can reference it in a later event's ``caused_by_event_ids`` before the
  writer has seen either event (the two-clock rule).

We generate ULIDs in-house rather than take a third-party dependency: the
algorithm is small and fully specified, and a research instrument benefits from
controlling its own id format. The generator is **monotonic within a
millisecond** — successive ids minted in the same millisecond strictly increase
— so even ids created in a tight loop sort in creation order.
"""

from __future__ import annotations

import os
import threading
import time

# Crockford's Base32 alphabet (excludes I, L, O, U to avoid ambiguity).
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(_ALPHABET)}

_TIME_BITS = 48
_RANDOM_BITS = 80
_TIME_MAX = (1 << _TIME_BITS) - 1
_RANDOM_MAX = (1 << _RANDOM_BITS) - 1
_ULID_LEN = 26


def _encode(value: int, length: int) -> str:
    """Encode ``value`` as ``length`` Crockford-Base32 chars (big-endian, 5 bits/char)."""
    chars = [""] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(chars)


class _Generator:
    """Monotonic ULID generator (thread-safe).

    Within a single millisecond, randomness is incremented rather than
    re-rolled, guaranteeing strict monotonicity of the rendered string. Across
    milliseconds the timestamp advances and randomness is re-rolled.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_ms = -1
        self._last_random = 0

    def new(self) -> str:
        with self._lock:
            ms = int(time.time() * 1000)
            if ms <= self._last_ms:
                # Same (or backwards) clock tick: keep the last timestamp and
                # increment randomness so the id still strictly increases.
                ms = self._last_ms
                self._last_random += 1
                if self._last_random > _RANDOM_MAX:
                    # Randomness overflow in one ms (astronomically unlikely):
                    # spill into the next millisecond and re-roll.
                    ms += 1
                    self._last_random = int.from_bytes(os.urandom(10), "big")
            else:
                self._last_random = int.from_bytes(os.urandom(10), "big")
            self._last_ms = ms

            if ms > _TIME_MAX:  # pragma: no cover — year ~10889
                raise ValueError("ULID timestamp overflow")
            return _encode(ms, 10) + _encode(self._last_random & _RANDOM_MAX, 16)


_default = _Generator()


def new_ulid() -> str:
    """Return a fresh, monotonic ULID string (26 Crockford-Base32 chars)."""
    return _default.new()


def gen_event_id() -> str:
    """Alias used by trace producers (matches M1 §3.2 naming)."""
    return new_ulid()


def is_ulid(value: str) -> bool:
    """True iff ``value`` is a syntactically valid ULID string."""
    if not isinstance(value, str) or len(value) != _ULID_LEN:
        return False
    return all(c in _DECODE for c in value)


def timestamp_ms(value: str) -> int:
    """Extract the millisecond timestamp embedded in a ULID."""
    if not is_ulid(value):
        raise ValueError(f"not a ULID: {value!r}")
    ms = 0
    for c in value[:10]:
        ms = (ms << 5) | _DECODE[c]
    return ms
