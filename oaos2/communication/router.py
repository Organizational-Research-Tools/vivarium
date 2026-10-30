"""Validate message kinds and check restricted text before delivery.

restricted_substrings maps each recipient to text it must not receive. The
check uses exact substring matching, not hashing: copies of those strings are
blocked, but paraphrases and partial copies may pass. The router returns a
verdict or raises ProtocolViolationError; runtime callers emit the relevant
event and decide delivery. It does not detect semantic leakage automatically.
See docs/mechanism/DEFERRED.md §7 for paths that do not call this check."""

from __future__ import annotations

from oaos2.communication.messages import COMM_KIND_REGISTRY
from oaos2.registry import Registry, RegistryError


class Router:
    def __init__(
        self,
        *,
        kind_registry: Registry[str] = COMM_KIND_REGISTRY,
        restricted_substrings: dict[str, frozenset[str]] | None = None,
    ):
        """Set allowed message kinds and the exact strings restricted for each recipient."""
        self.kind_registry = kind_registry
        self.restricted_substrings = restricted_substrings or {}

    def validate_kind(self, kind: str) -> str:
        """Return the primitive for ``kind``; raise on an unregistered kind."""
        try:
            return self.kind_registry[kind]
        except RegistryError as exc:
            raise ProtocolViolationError(f"unknown communication kind {kind!r}") from exc

    def relay_blocked(self, payload: str, recipient_agent_id: str) -> bool:
        """Return True if the payload contains a nonempty restricted string exactly.

        Paraphrases and partial copies can pass. This method returns a verdict only;
        callers handle delivery and event recording. It does not classify meaning."""
        for secret in self.restricted_substrings.get(recipient_agent_id, frozenset()):
            if secret and secret in payload:
                return True
        return False


class ProtocolViolationError(Exception):
    """An unregistered kind / malformed message (→ protocol.violation)."""
