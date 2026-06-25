"""Destructive command and risk patterns."""

from __future__ import annotations

DESTRUCTIVE_PATTERNS: list[tuple[str, str, str]] = [
    ("--yes-i-really-really-mean-it", "error", "Requires dangerous confirmation flag"),
    ("--yes-i-really-mean-it", "error", "Requires dangerous confirmation flag"),
    ("--force", "warning", "Force flag bypasses safety checks"),
    ("osd purge", "error", "Permanently removes OSD data"),
    ("osd destroy", "error", "Destroys OSD permanently"),
    ("osd rm", "warning", "Removes OSD from cluster"),
    ("pool delete", "warning", "Deletes pool and all contained data"),
    ("pool rm", "warning", "Removes pool and all contained data"),
    ("rm-cluster", "error", "Removes entire Ceph cluster"),
    ("rm-daemon", "warning", "Removes a running daemon"),
    ("zap-osds", "warning", "Wipes OSD devices"),
    ("fs rm", "error", "Removes a CephFS filesystem"),
    ("fs volume rm", "error", "Removes a CephFS volume"),
    ("nfs cluster delete", "warning", "Deletes NFS cluster"),
    ("rbd rm", "warning", "Deletes an RBD image"),
    ("rbd trash purge", "warning", "Permanently removes all trashed images"),
    ("rbd snap purge", "warning", "Deletes all snapshots of an image"),
    ("blocklist add", "warning", "Blocklists a client from the cluster"),
    ("osd set noout", "info", "Sets noout flag — prevents OSD rebalancing"),
    ("osd set noin", "info", "Sets noin flag — prevents new OSDs from joining"),
    ("osd set noscrub", "info", "Disables scrubbing"),
    ("osd set nodeep-scrub", "info", "Disables deep scrubbing"),
]
