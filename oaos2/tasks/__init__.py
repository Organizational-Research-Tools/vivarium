"""Load task materials, outcome requirements, scoring, and task-specific plugins.

Each library/tasks/<pack>/manifest.yaml selects visible materials, private
references, role instructions, contract profiles, and scoring inputs. Several task
families share this machinery; paper replication is a historical first use,
not the only supported task. See docs/experiments/README.md for current studies."""

from oaos2.tasks.pack import RolePacket, TaskPack

__all__ = ["RolePacket", "TaskPack"]
