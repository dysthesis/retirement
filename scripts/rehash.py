#!/usr/bin/env python3
"""Refresh the Packwiz hash chain, optionally re-pinning selected downloads."""

import base64
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


root = Path(__file__).resolve().parent.parent
pack_root = root / "packwiz"


def replace_download_hash(original, digest):
    parsed = tomllib.loads(original)
    expected = parsed | {"download": parsed["download"] | {"hash": digest}}
    lines = original.splitlines(keepends=True)
    table = ""
    replacements = 0

    for number, line in enumerate(lines):
        if line.lstrip().startswith("["):
            table = line.partition("#")[0].strip()

        if table == "[download]":
            lines[number], count = re.subn(
                r'''^(\s*hash\s*=\s*)(['"])[^'"]*\2''',
                lambda match: f"{match[1]}{match[2]}{digest}{match[2]}",
                line,
            )
            replacements += count

    updated = "".join(lines)
    if replacements != 1 or tomllib.loads(updated) != expected:
        raise ValueError("Expected one unambiguous [download].hash assignment")

    return updated


def main():
    pack = tomllib.loads((pack_root / "pack.toml").read_text())
    index = tomllib.loads((pack_root / pack["index"]["file"]).read_text())
    indexed = {entry["file"] for entry in index["files"] if entry.get("metafile", False)}
    selected = list(dict.fromkeys(
        str((pack_root / name).resolve().relative_to(pack_root)) for name in sys.argv[1:]
    ))

    if unknown := set(selected) - indexed:
        raise ValueError(f"Not indexed Packwiz metafiles: {sorted(unknown)}")

    originals = {name: (pack_root / name).read_text() for name in selected}
    updates = {}

    if selected:
        expression = '''{ paths }: let
          flake = builtins.getFlake (toString ./.);
          pkgs = flake.inputs.nixpkgs.legacyPackages.${builtins.currentSystem};
          resolve = pkgs.callPackage ./nix/lib/download.nix {};
        in map (file: let
          mod = builtins.fromTOML (builtins.readFile (./packwiz + "/${file}"));
          data = resolve mod;
          download = pkgs.fetchurl data;
        in {
          inherit file;
          inherit (data) url outputHashAlgo;
          name = download.name;
        }) (builtins.fromJSON paths)'''

        result = subprocess.run([
            "nix-instantiate", "--eval", "--strict", "--json", "--expr", expression,
            "--argstr", "paths", json.dumps(selected),
        ], cwd=root, check=True, stdout=subprocess.PIPE, text=True)

        for entry in json.loads(result.stdout):
            print(f"Prefetching {entry['file']}...", flush=True)
            result = subprocess.run([
                "nix", "store", "prefetch-file", "--json",
                "--name", entry["name"], "--hash-type", entry["outputHashAlgo"], entry["url"],
            ], check=True, stdout=subprocess.PIPE, text=True)

            algorithm, encoded = json.loads(result.stdout)["hash"].split("-", 1)
            if algorithm != entry["outputHashAlgo"]:
                raise ValueError(f"Unexpected prefetch hash algorithm: {algorithm}")

            digest = base64.b64decode(encoded, validate=True).hex()
            updates[entry["file"]] = replace_download_hash(originals[entry["file"]], digest)

    for name, original in originals.items():
        if (pack_root / name).read_text() != original:
            raise RuntimeError(f"Changed during prefetch: {name}")

    for name, updated in updates.items():
        if updated == originals[name]:
            continue

        path = pack_root / name
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            try:
                temporary.write(updated)
                temporary.flush()
                os.chmod(temporary_path, path.stat().st_mode & 0o777)
                os.replace(temporary_path, path)
            finally:
                temporary_path.unlink(missing_ok=True)

    subprocess.run(["packwiz", "refresh"], cwd=pack_root, check=True)


if __name__ == "__main__":
    with (root / ".rehash.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        main()
