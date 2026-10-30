"""Workspace areas, file permissions, write capture, and file-version histories.

Zone classes describe the kind of access; Docker mounts enforce container access
and FileAccessPolicy controls host-mediated tools. WorkspaceManager records
writes and scans private scratch after command execution."""

from oaos2.workspace.acl import (
    AccessDenied,
    Enforcement,
    FileAccessPolicy,
    Zone,
    resolve_file_access_policy,
)
from oaos2.workspace.monitor import WorkspaceManager, canonical_real_path
from oaos2.workspace.zones import (
    ZONE_CLASSES,
    MountMode,
    ZoneClass,
    zone_class_mount_mode,
)

__all__ = [
    "ZONE_CLASSES",
    "AccessDenied",
    "Enforcement",
    "FileAccessPolicy",
    "MountMode",
    "WorkspaceManager",
    "Zone",
    "ZoneClass",
    "canonical_real_path",
    "resolve_file_access_policy",
    "zone_class_mount_mode",
]
