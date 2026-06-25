"""Create-to-cleanup command mapping for resource lifecycle tracking."""

from __future__ import annotations

CLEANUP_PAIRS: dict[str, list[str]] = {
    "ceph osd pool create": ["ceph osd pool delete", "ceph osd pool rm"],
    "ceph fs volume create": ["ceph fs volume rm"],
    "ceph fs new": ["ceph fs rm"],
    "ceph nfs cluster create": ["ceph nfs cluster delete", "ceph nfs cluster rm"],
    "ceph nfs export create": ["ceph nfs export delete", "ceph nfs export rm"],
    "ceph auth add": ["ceph auth rm", "ceph auth del"],
    "ceph auth get-or-create": ["ceph auth rm", "ceph auth del"],
    "ceph osd tier add": ["ceph osd tier remove"],
    "ceph mgr module enable": ["ceph mgr module disable"],
    "rbd create": ["rbd remove", "rbd rm"],
    "rbd clone": ["rbd remove", "rbd rm"],
    "rbd snap create": ["rbd snap remove", "rbd snap rm"],
    "rbd snap protect": ["rbd snap unprotect"],
    "rbd mirror pool enable": ["rbd mirror pool disable"],
    "rbd mirror image enable": ["rbd mirror image disable"],
    "rbd namespace create": ["rbd namespace remove", "rbd namespace rm"],
    "rbd group create": ["rbd group remove", "rbd group rm"],
    "rbd pool init": [],
    "rbd trash move": ["rbd trash remove", "rbd trash restore"],
    "cephadm bootstrap": ["cephadm rm-cluster"],
    "cephadm deploy": ["cephadm rm-daemon"],
    "ceph-volume lvm create": ["ceph-volume lvm zap"],
    "rados mksnap": ["rados rmsnap"],
    "rados put": ["rados rm"],
}


def get_create_command(command_name: str) -> str | None:
    """Normalize a command to its create-form key, if it matches."""
    for create_cmd in CLEANUP_PAIRS:
        parts = create_cmd.split()
        cmd_parts = command_name.split()
        if cmd_parts[:len(parts)] == parts:
            return create_cmd
    return None


def get_cleanup_commands(create_command: str) -> list[str]:
    """Get the expected cleanup commands for a create command."""
    return CLEANUP_PAIRS.get(create_command, [])


def is_cleanup_command(command_name: str) -> str | None:
    """Check if a command is a cleanup for some create command. Returns the create command."""
    cmd_parts = command_name.split()
    for create_cmd, cleanups in CLEANUP_PAIRS.items():
        for cleanup in cleanups:
            cleanup_parts = cleanup.split()
            if cmd_parts[:len(cleanup_parts)] == cleanup_parts:
                return create_cmd
    return None
