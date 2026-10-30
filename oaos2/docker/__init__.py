"""Isolate tool execution and capture work from host-backed directories.

The host manages agent loops and credentials. Containers execute tools with the
mounts and limits permitted by DockerPolicy. Persistent scratch files live on the
host and can be captured after container failure; temporary container storage is
separate and may not survive. See docs/SYSTEM.md and docs/RUNBOOK.md."""

from oaos2.docker.backend import (
    BackendCapabilities,
    ContainerBackend,
    ContainerHandle,
    ExecResult,
    FakeContainerBackend,
    LocalDockerBackend,
)
from oaos2.docker.isolation import IsolationViolation
from oaos2.docker.policy import DockerPolicy, Mount, resolve_docker_policy

__all__ = [
    "BackendCapabilities",
    "ContainerBackend",
    "ContainerHandle",
    "DockerPolicy",
    "ExecResult",
    "FakeContainerBackend",
    "IsolationViolation",
    "LocalDockerBackend",
    "Mount",
    "resolve_docker_policy",
]
