#!/usr/bin/env python3
"""Import Ceph config parameters into the knowledge base.

Supports both TSV formats:
  - Reference TSV (13 columns: name, type, level, default, desc, ...)
  - Defaults TSV (4 columns: daemon_type, name, value, source)

Usage:
    python import_configs.py --reference ceph_config_reference.tsv
    python import_configs.py --defaults ceph_config_all_defaults.tsv
    python import_configs.py --reference ref.tsv --defaults defaults.tsv
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ceph_command_kb.log import setup_logging
from ceph_command_kb.storage.config_loader import (
    load_defaults_tsv,
    load_reference_tsv,
    merge_configs,
    write_configs_json,
)

KB_DIR = Path("knowledge/ceph-20.2.1-tentacle")


def main():
    parser = argparse.ArgumentParser(description="Import Ceph configs into the knowledge base")
    parser.add_argument(
        "--reference", "-r",
        type=Path,
        help="Reference TSV (13 columns: name, type, level, default, desc, ...)",
    )
    parser.add_argument(
        "--defaults", "-d",
        type=Path,
        help="Defaults TSV (4 columns: daemon_type, name, value, source)",
    )
    parser.add_argument(
        "--kb-dir",
        type=Path,
        default=KB_DIR,
        help=f"Knowledge base directory (default: {KB_DIR})",
    )
    args = parser.parse_args()

    if not args.reference and not args.defaults:
        parser.error("At least one of --reference or --defaults is required")

    logger = setup_logging(level="INFO")

    reference = {}
    defaults = {}

    if args.reference:
        reference = load_reference_tsv(args.reference)
        logger.info("Reference: %d params", len(reference))

    if args.defaults:
        defaults = load_defaults_tsv(args.defaults)
        logger.info("Defaults: %d params", len(defaults))

    if reference and defaults:
        configs = merge_configs(reference, defaults)
    elif reference:
        configs = reference
    else:
        configs = defaults

    with_desc = sum(1 for c in configs.values() if c.desc)
    with_type = sum(1 for c in configs.values() if c.type)
    with_defaults = sum(1 for c in configs.values() if c.daemon_defaults)

    logger.info("Total configs: %d", len(configs))
    logger.info("  With description: %d", with_desc)
    logger.info("  With type: %d", with_type)
    logger.info("  With daemon defaults: %d", with_defaults)

    write_configs_json(configs, args.kb_dir)
    logger.info("Written to %s/configs.json", args.kb_dir)


if __name__ == "__main__":
    main()
