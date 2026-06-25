#!/usr/bin/env python3
"""Update the knowledge base with manually provided help texts.

Processes raw help output and merges results into the existing KB
without requiring Ceph binaries or cluster access.

Usage:
    python update_from_help.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ceph_command_kb.models import Argument, ArgumentType, Command, Flag, KnowledgeBase
from ceph_command_kb.parsing.registry import ParserRegistry
from ceph_command_kb.storage.json_writer import JsonWriter
from ceph_command_kb.storage.markdown_writer import MarkdownWriter
from ceph_command_kb.storage.raw_help_writer import RawHelpWriter
from ceph_command_kb.storage.search_index import SearchIndexWriter

KB_DIR = Path("knowledge/ceph-20.2.1-tentacle")

HELP_TEXTS = {}

HELP_TEXTS["ceph-authtool"] = """\
usage: ceph-authtool keyringfile [OPTIONS]...
where the options are:
  -l, --list                    will list all keys and capabilities present in
                                the keyring
  -p, --print-key               will print an encoded key for the specified
                                entityname. This is suitable for the
                                'mount -o secret=..' argument
  -C, --create-keyring          will create a new keyring, overwriting any
                                existing keyringfile
  -g, --gen-key                 will generate a new secret key for the
                                specified entityname
  --gen-print-key               will generate a new secret key without set it
                                to the keyringfile, prints the secret to stdout
  --import-keyring FILE         will import the content of a given keyring
                                into the keyringfile
  -n NAME, --name NAME          specify entityname to operate on
  -a BASE64, --add-key BASE64   will add an encoded key to the keyring
  --cap SUBSYSTEM CAPABILITY    will set the capability for given subsystem
  --caps CAPSFILE               will set all of capabilities associated with a
                                given key, for all subsystems
  --mode MODE                   will set the desired file mode to the keyring
                                e.g: '0644', defaults to '0600'\
"""

HELP_TEXTS["ceph-volume"] = """\
usage: ceph-volume [-h] [--cluster CLUSTER] [--log-level {debug,info,warning,error,critical}] [--log-path LOG_PATH]

ceph-volume: Deploy Ceph OSDs using different device technologies like lvm or
physical disks.

Available subcommands:

lvm                      Use LVM and LVM-based technologies to deploy OSDs
simple                   Manage already deployed OSDs with ceph-volume
raw                      Manage single-device OSDs on raw block devices
inventory                Get this nodes available disk inventory
activate                 Activate an OSD
drive-group              Deploy OSDs according to a drive groups specification.

optional arguments:
  -h, --help            show this help message and exit
  --cluster CLUSTER     Cluster name (defaults to "ceph")
  --log-level {debug,info,warning,error,critical}
                        Change the file log level (defaults to debug)
  --log-path LOG_PATH   Change the log path (defaults to /var/log/ceph)\
"""

HELP_TEXTS["ceph-bluestore-tool"] = """\
All options:

Options:
  -h [ --help ]                   produce help message
  -i arg                          OSD instance
  --path arg                      bluestore path
  --data-path arg                 --path alias
  --out-dir arg                   output directory
  --input-file arg                import file
  --dest-file arg                 destination file
  -l [ --log-file ] arg           log file
  --log-level arg                 log level (30=most, 20=lots, 10=some, 1=little)
  --dev arg                       device(s)
  --devs-source arg               bluefs-dev-migrate source device(s)
  --dev-target arg                target/resulting device
  --deep arg                      deep fsck (read all data)
  -k [ --key ] arg                label metadata key name
  -v [ --value ] arg              label metadata value
  --allocator arg                 allocator to inspect
  --bdev-type arg                 bdev type to inspect
  --yes-i-really-really-mean-it   additional confirmation for dangerous commands
  --sharding arg                  new sharding to apply
  --resharding-ctrl arg           gives control over resharding procedure details
  --offset arg                    disk location
  --op arg                        --command alias

Positional options:
  --command arg                   fsck, qfsck, allocmap, restore_cfb, repair,
                                  quick-fix, bluefs-export, bluefs-import,
                                  bluefs-bdev-sizes, bluefs-bdev-expand,
                                  bluefs-bdev-new-db, bluefs-bdev-new-wal,
                                  bluefs-bdev-migrate, show-label,
                                  show-label-at, set-label-key, rm-label-key,
                                  prime-osd-dir, bluefs-super-dump,
                                  bluefs-log-dump, free-dump, free-score,
                                  free-fragmentation, bluefs-stats, reshard,
                                  show-sharding, trim, zap-device,
                                  revert-wal-to-plain\
"""

HELP_TEXTS["ceph-objectstore-tool"] = """\
Allowed options:
  --help                      produce help message
  --type arg                  Arg is one of [bluestore (default), memstore]
  --data-path arg             path to object store, mandatory
  --target-version arg        the target version for log expansion
  --journal-path arg          path to journal
  --pgid arg                  PG id, mandatory for info, log, remove, export, export-remove, mark-complete, trim-pg-log, trim-pg-log-dups
  --pool arg                  Pool name
  --op arg                    Arg is one of [info, log, remove, mkfs, fsck, repair, fuse, dup, export, export-remove, import, list, list-slow-omap, fix-lost, list-pgs, dump-super, meta-list, get-osdmap, set-osdmap, get-superblock, set-superblock, get-inc-osdmap, set-inc-osdmap, mark-complete, reset-last-complete, update-mon-db, dump-export, trim-pg-log, trim-pg-log-dups statfs]
  --epoch arg                 epoch# for get-osdmap and get-inc-osdmap
  --file arg                  path of file for import/export operations
  --mon-store-path arg        path of monstore to update-mon-db
  --fsid arg                  fsid for new store created by mkfs
  --target-data-path arg      path of target object store (for --op dup)
  --mountpoint arg            fuse mountpoint
  --format arg (=json-pretty) Output format (json, json-pretty, xml, xml-pretty)
  --debug                     Enable diagnostic output to stderr
  --no-mon-config             Do not contact mons for config
  --no-superblock             Do not read superblock
  --force                     Ignore some types of errors - USE WITH CAUTION
  --skip-journal-replay       Disable journal replay
  --skip-mount-omap           Disable mounting of omap
  --head                      Find head/snapdir when searching for objects by name
  --dry-run                   Don't modify the objectstore
  --tty                       Treat stdout as a tty (no binary data)
  --namespace arg             Specify namespace when searching for objects
  --rmtype arg                Specify corrupting object removal type - TESTING USE ONLY
  --slow-omap-threshold arg   Threshold (in seconds) for slow omap listing\
"""

HELP_TEXTS["crushtool"] = """\
usage: crushtool ...

Display, modify and test a crush map

There are five stages, running one after the other:
 - input/build
 - tunables adjustments
 - modifications
 - display/test
 - output

Options:
   --decompile|-d map    decompile a crush map to source
   --compile|-c map.txt  compile a map from source
   --enable-unsafe-tunables  compile with unsafe tunables
   --build --num_osds N layer1 ...  build a new map
   --set-choose-local-tries N  set choose local retries
   --set-choose-local-fallback-tries N  set choose local fallback retries
   --set-choose-total-tries N  set choose total descent attempts
   --set-chooseleaf-descend-once <0|1>  set chooseleaf retry behavior
   --set-chooseleaf-vary-r <0|1>  set chooseleaf vary r based on parent
   --set-chooseleaf-stable <0|1>  set chooseleaf firstn stable results
   --add-item id weight name  insert an item into the hierarchy
   --update-item id weight name  insert or move an item
   --remove-item name  remove the given item
   --reweight-item name weight  reweight a given item
   --add-bucket name type  insert a bucket into the hierarchy
   --move name --loc type name ...  move the given item
   --reweight  recalculate all bucket weights
   --rebuild-class-roots  rebuild the per-class shadow trees
   --create-simple-rule name root type mode  create crush rule
   --create-replicated-rule name root type  create replicated crush rule
   --device-class <class>  use device class for new rule
   --remove-rule name  remove the specified crush rule
   --dump  dump the crush map
   --tree  print map summary as a tree
   --bucket-tree  print bucket map summary as a tree
   --check [max_id]  check if any item references unknown name/type
   --show-location id  show location for given device id
   --test  test a range of inputs on the map
   --show-utilization  show OSD usage
   --show-statistics  show chi squared statistics
   --show-mappings  show mappings
   --show-bad-mappings  show bad mappings
   --show-choose-tries  show choose tries histogram
   --reclassify  transform legacy CRUSH map buckets and rules
   --set-subtree-class <bucket-name> <class>  set class for items beneath bucket
   --compare <otherfile>  compare two maps\
"""

HELP_TEXTS["monmaptool"] = """\
usage: monmaptool [--print] [--create [--clobber] [--fsid uuid]]
        [--enable-all-features]
        [--generate] [--set-initial-members]
        [--add name 1.2.3.4:567] [--rm name]
        [--addv name [v2:1.2.4.5:567,v1:1.2.3.4:568]]
        [--feature-list [plain|parseable]]
        [--feature-set <value> [--optional|--persistent]]
        [--feature-unset <value> [--optional|--persistent]]
        [--set-min-mon-release <release-major-number>]
        <mapfilename>\
"""

HELP_TEXTS["osdmaptool"] = """\
 usage: [--print] <mapfilename>
   --create-from-conf      creates an osd map with default configurations
   --createsimple <numosd> creates a relatively generic OSD map with <numosd> devices
   --pgp-bits <bits>       pgp_num map attribute will be shifted by <bits>
   --pg-bits <bits>        pg_num map attribute will be shifted by <bits>
   --clobber               allows osdmaptool to overwrite <mapfilename>
   --export-crush <file>   write osdmap's crush map to <file>
   --import-crush <file>   replace osdmap's crush map with <file>
   --health                dump health checks
   --test-map-pgs          map all pgs
   --test-map-pgs-dump     map all pgs (dump)
   --test-map-pgs-dump-all map all pgs to osds
   --mark-up-in            mark osds up and in
   --mark-out <osdid>      mark an osd as out
   --mark-up <osdid>       mark an osd as up
   --mark-in <osdid>       mark an osd as in
   --with-default-pool     include default pool when creating map
   --clear-temp            clear pg_temp and primary_temp
   --clean-temps           clean pg_temps
   --test-random           do random placements
   --test-map-pg <pgid>    map a pgid to osds
   --test-map-object <objectname>  map an object to osds
   --upmap-cleanup <file>  clean up pg_upmap entries
   --upmap <file>          calculate pg upmap entries to balance pg layout
   --upmap-max <max-count> set max upmap entries to calculate
   --upmap-deviation <max-deviation>  max deviation from target
   --upmap-pool <poolname> restrict upmap balancing to pool
   --upmap-active          keep applying changes until balanced
   --dump <format>         displays the map in plain text or json
   --tree                  displays a tree of the map
   --test-crush            map pgs to acting osds
   --adjust-crush-weight   change CRUSH weight
   --save                  write modified osdmap with changes
   --read <file>           calculate pg upmap entries for primaries
   --read-pool <poolname>  specify pool for read balancer
   --osd-size-aware        account for devices of different sizes
   --vstart                prefix output with './bin/'\
"""


def parse_flags_generic(text: str) -> list[Flag]:
    """Extract flags from various help formats."""
    flags = []
    seen = set()
    
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        
        # Pattern: -s, --long-form ARG    description
        m = re.match(
            r"(-\w)\s*(?:[,|]\s*|\s+)(--[\w-]+)(?:\s+(\S+))?\s{2,}(.+)", stripped
        )
        if m:
            key = (m.group(1), m.group(2))
            if key not in seen:
                seen.add(key)
                flags.append(Flag(
                    short_form=m.group(1), long_form=m.group(2),
                    description=m.group(4).strip(),
                    takes_value=m.group(3) is not None,
                    value_name=m.group(3),
                ))
            continue
        
        # Pattern: -s [ --long ] arg    description (boost style)
        m = re.match(
            r"(-\w)\s*\[\s*--([\w-]+)\s*\](?:\s+(\S+))?\s{2,}(.+)", stripped
        )
        if m:
            key = (m.group(1), f"--{m.group(2)}")
            if key not in seen:
                seen.add(key)
                flags.append(Flag(
                    short_form=m.group(1), long_form=f"--{m.group(2)}",
                    description=m.group(4).strip(),
                    takes_value=m.group(3) is not None,
                    value_name=m.group(3),
                ))
            continue
        
        # Pattern: --long-form ARG    description
        m = re.match(r"(--[\w-]+)(?:\s+(\S+))?\s{2,}(.+)", stripped)
        if m:
            key = (None, m.group(1))
            if key not in seen:
                seen.add(key)
                flags.append(Flag(
                    long_form=m.group(1),
                    description=m.group(3).strip(),
                    takes_value=m.group(2) is not None,
                    value_name=m.group(2),
                ))
            continue
        
        # Pattern: --long-form|-short    description (crushtool style)
        m = re.match(r"(--[\w-]+)\|(-\w)\s+(.+)", stripped)
        if m:
            key = (m.group(2), m.group(1))
            if key not in seen:
                seen.add(key)
                flags.append(Flag(
                    short_form=m.group(2), long_form=m.group(1),
                    description=m.group(3).strip(),
                ))
            continue
    
    return flags


def extract_keywords(name: str, desc: str) -> list[str]:
    stop = {"a","an","the","is","are","to","of","in","for","on","with","at","by","from","and","or","not","this","that","it","its","will"}
    kw = set()
    for w in name.split():
        kw.add(w.lower())
        if "-" in w:
            kw.update(w.lower().split("-"))
    for w in re.findall(r"\w+", desc.lower()):
        if len(w) > 2 and w not in stop:
            kw.add(w)
    return sorted(kw)


def main():
    # Load existing KB
    commands_path = KB_DIR / "commands.json"
    with open(commands_path) as f:
        kb_data = json.load(f)
    
    existing = {cmd["name"]: cmd for cmd in kb_data["commands"]}
    added = 0
    updated = 0

    for binary, help_text in HELP_TEXTS.items():
        flags = parse_flags_generic(help_text)
        
        # Extract usage
        usage_match = re.search(r"^usage:\s*(.+)$", help_text, re.IGNORECASE | re.MULTILINE)
        usage = usage_match.group(1).strip() if usage_match else None
        
        # Extract description from first non-empty, non-usage line
        desc = ""
        past_usage = False
        for line in help_text.split("\n"):
            s = line.strip()
            if s.lower().startswith("usage:"):
                past_usage = True
                continue
            if past_usage and s and not s.startswith("-") and not s.startswith("[") and not s.endswith(":"):
                if not re.match(r"^(where|options|positional|available|environ|log)", s, re.IGNORECASE):
                    desc = s
                    break
        
        # Update existing entry
        if binary in existing:
            existing[binary]["flags"] = [f.to_dict() for f in flags]
            if usage:
                existing[binary]["usage"] = usage
            if desc:
                existing[binary]["description"] = desc
            existing[binary]["raw_help"] = help_text
            existing[binary]["keywords"] = extract_keywords(binary, desc)
            updated += 1
            print(f"  Updated {binary}: {len(flags)} flags")
        
        # Extract ceph-volume subcommands
        if binary == "ceph-volume":
            subcmds = {
                "ceph-volume lvm": "Use LVM and LVM-based technologies to deploy OSDs",
                "ceph-volume simple": "Manage already deployed OSDs with ceph-volume",
                "ceph-volume raw": "Manage single-device OSDs on raw block devices",
                "ceph-volume inventory": "Get this nodes available disk inventory",
                "ceph-volume activate": "Activate an OSD",
                "ceph-volume drive-group": "Deploy OSDs according to a drive groups specification",
            }
            sub_names = []
            for name, sub_desc in subcmds.items():
                sub_names.append(name.split()[-1])
                if name not in existing:
                    existing[name] = Command(
                        name=name, binary="ceph-volume",
                        parts=name.split(), description=sub_desc,
                        raw_help=f"(Extracted from ceph-volume -h)",
                        discovery_path=f"ceph-volume -> {name}",
                        keywords=extract_keywords(name, sub_desc),
                    ).to_dict()
                    added += 1
                    print(f"  Added {name}")
            existing["ceph-volume"]["subcommands"] = sub_names

    # Rebuild commands list
    kb_data["commands"] = sorted(existing.values(), key=lambda c: c["name"])
    kb_data["total_commands"] = len(kb_data["commands"])
    
    with open(commands_path, "w") as f:
        json.dump(kb_data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    
    print(f"\nUpdated {updated} commands, added {added} new commands")
    print(f"Total: {kb_data['total_commands']} commands")
    
    # Regenerate markdown, search index, raw help
    from ceph_command_kb.models import CephVersion
    # Convert list format to dict format for KnowledgeBase.from_dict
    kb_dict = dict(kb_data)
    kb_dict["commands"] = {cmd["name"]: cmd for cmd in kb_data["commands"]}
    kb = KnowledgeBase.from_dict(kb_dict)
    
    MarkdownWriter(KB_DIR).write(kb)
    SearchIndexWriter(KB_DIR).write(kb)
    RawHelpWriter(KB_DIR).write(kb)
    
    # Update metadata
    JsonWriter(KB_DIR)._write_metadata(kb)
    
    print("Regenerated markdown, search index, and raw help files")


if __name__ == "__main__":
    main()
