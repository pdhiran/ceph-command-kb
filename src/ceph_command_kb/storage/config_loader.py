"""Load Ceph config parameters from TSV files.

Supports two TSV formats:
1. Reference format (from capture_config_reference.sh):
   name, type, level, default, desc, long_desc, can_update_at_runtime,
   services, min, max, enum_allowed, tags, flags

2. Defaults format (from capture_config_defaults.sh):
   daemon_type, name, value, source
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from ceph_command_kb.models import ConfigOption

logger = logging.getLogger(__name__)


def load_reference_tsv(path: Path) -> dict[str, ConfigOption]:
    """Load the full reference TSV (13-column format)."""
    configs: dict[str, ConfigOption] = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue

            services_raw = row.get("services", "")
            services = [s.strip() for s in services_raw.split(",") if s.strip()] if services_raw else []

            enum_raw = row.get("enum_allowed", "")
            enum_allowed = [e.strip() for e in enum_raw.split(",") if e.strip()] if enum_raw else []

            tags_raw = row.get("tags", "")
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

            flags_raw = row.get("flags", "")
            flags = [fl.strip() for fl in flags_raw.split(",") if fl.strip()] if flags_raw else []

            can_update = row.get("can_update_at_runtime", "").lower() in ("true", "yes", "1")

            configs[name] = ConfigOption(
                name=name,
                type=row.get("type", ""),
                level=row.get("level", ""),
                default=row.get("default", ""),
                desc=row.get("desc", ""),
                long_desc=row.get("long_desc", ""),
                can_update_at_runtime=can_update,
                services=services,
                min=row.get("min", ""),
                max=row.get("max", ""),
                enum_allowed=enum_allowed,
                tags=tags,
                flags=flags,
            )

    logger.info("Loaded %d config options from reference TSV: %s", len(configs), path)
    return configs


def load_defaults_tsv(path: Path) -> dict[str, ConfigOption]:
    """Load the per-daemon defaults TSV (4-column format).

    Merges multiple daemon rows into a single ConfigOption per param.
    """
    configs: dict[str, ConfigOption] = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            daemon_type = row.get("daemon_type", "").strip()
            name = row.get("name", "").strip()
            value = row.get("value", "")
            source = row.get("source", "")

            if not name:
                continue

            if name not in configs:
                configs[name] = ConfigOption(name=name)

            cfg = configs[name]
            cfg.daemon_defaults[daemon_type] = value

            if daemon_type not in cfg.services:
                cfg.services.append(daemon_type)

            if source == "default" and not cfg.default:
                cfg.default = value

    logger.info("Loaded %d config options from defaults TSV: %s", len(configs), path)
    return configs


def merge_configs(
    reference: dict[str, ConfigOption],
    defaults: dict[str, ConfigOption],
) -> dict[str, ConfigOption]:
    """Merge reference metadata with per-daemon defaults.

    Reference data takes precedence for metadata fields.
    Defaults data provides daemon_defaults and services.
    """
    merged = dict(reference)

    for name, def_cfg in defaults.items():
        if name in merged:
            merged[name].daemon_defaults.update(def_cfg.daemon_defaults)
            for svc in def_cfg.services:
                if svc not in merged[name].services:
                    merged[name].services.append(svc)
            if not merged[name].default and def_cfg.default:
                merged[name].default = def_cfg.default
        else:
            merged[name] = def_cfg

    logger.info("Merged configs: %d total", len(merged))
    return merged


def write_configs_json(configs: dict[str, ConfigOption], output_dir: Path) -> None:
    """Write configs.json to the knowledge base directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "configs.json"

    data = {
        "total_configs": len(configs),
        "configs": [cfg.to_dict() for cfg in sorted(configs.values(), key=lambda c: c.name)],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    logger.info("Wrote %d configs to %s", len(configs), path)
