"""Explicit, dry-run-first wrapper for importing a copied legacy fixture tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sadaf.migration import migrate_legacy
from sadaf.settings import SettingsError, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Copied legacy fixture directory")
    parser.add_argument("--target", type=Path, required=True, help="Separate SQLite destination")
    parser.add_argument("--user-id", default="default")
    parser.add_argument("--apply", action="store_true", help="Apply the planned import; existing targets are backed up")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        report = migrate_legacy(args.source, args.target, user_id=args.user_id,
                                apply=args.apply, legacy_root=settings.legacy_memory_dir)
    except (SettingsError, ValueError, OSError, sqlite3.Error) as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        return 2
    print(json.dumps({
        "mode": "applied" if report.applied else "dry-run",
        "already_imported": report.already_imported,
        "facts": report.facts,
        "edges": report.edges,
        "episodes": report.episodes,
        "digest": report.digest,
        "backup_created": report.backup is not None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
