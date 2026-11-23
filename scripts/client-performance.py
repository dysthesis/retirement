#!/usr/bin/env python3
"""Opt in to the pack's client defaults on an existing, stopped instance."""

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "packwiz/config/modpack_defaults/config"
FILES = {"voxy": "voxy-config.json", "emf": "entity_model_features.json"}


def read_object(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key in {path}: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Invalid JSON constant in {path}: {value}")

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                       parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def plan(instance, selected):
    changes = []
    for name in selected:
        path = instance / "config" / FILES[name]
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Expected generated config (regular file): {path}. Launch once first.")
        original = path.read_bytes()
        current = read_object(path)
        settings = read_object(DEFAULTS / FILES[name])
        updated = current | settings
        if updated != current:
            changes.append((path, original, current, updated, settings))
    return changes


def apply(changes):
    # Check all files before writing any. Do not run this with Minecraft open.
    for path, original, _, _, _ in changes:
        if path.read_bytes() != original:
            raise RuntimeError(f"Config changed since inspection: {path}")
    for path, original, _, updated, _ in changes:
        # mkstemp creates a unique backup; never replace an earlier backup.
        fd, backup = tempfile.mkstemp(prefix=path.name + ".retirement-backup-", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(original)
        shutil.copymode(path, backup)
        fd, tmp = tempfile.mkstemp(prefix=".retirement-config-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(updated, handle, indent=2, ensure_ascii=False, allow_nan=False)
                handle.write("\n")
            shutil.copymode(path, tmp)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        print(f"Updated {path}; backup: {backup}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path, help="Minecraft instance directory containing config/")
    parser.add_argument("--component", action="append", choices=tuple(FILES),
                        help="Repeat to select components; default: both")
    parser.add_argument("--apply", action="store_true", help="Write changes; default is preview only")
    args = parser.parse_args()
    selected = list(dict.fromkeys(args.component or FILES))
    changes = plan(args.instance.resolve(), selected)
    if not changes:
        print("No changes needed.")
        return
    for path, _, current, _, settings in changes:
        print(path)
        for key, value in settings.items():
            if key not in current or current[key] != value:
                print(f"  {key}: {current.get(key, '<absent>')!r} -> {value!r}")
    if args.apply:
        apply(changes)
    else:
        print("Preview only. Close Minecraft and repeat with --apply to write changes.")


if __name__ == "__main__":
    main()
