#!/usr/bin/env python3
"""Refresh the three fixed-output modpack hashes. Place in scripts/."""

import base64
import os
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
fake = "sha256-" + base64.b64encode(os.urandom(32)).decode()
sha256 = r"sha256-[A-Za-z0-9+/]{43}="
updates = {}

for package, filename in (
    ("modpack-client", "client.nix"),
    ("modpack-server", "server.nix"),
    ("modrinth", "modrinth.nix"),
):
    path = root / "nix/packages" / filename
    original = path.read_text()
    old = re.findall(sha256, original)
    if len(old) != 1:
        raise RuntimeError(f"Expected one hash in {path}")

    expr = (
        f'(builtins.getFlake ("git+file://" + toString ./.))'
        f".packages.${{builtins.currentSystem}}.{package}"
        f'.overrideAttrs (_: {{ outputHash = "{fake}"; }})'
    )
    result = subprocess.run(
        ["nix", "build", "--impure", "--no-link", "--expr", expr],
        cwd=root, capture_output=True, text=True,
    )
    got = re.findall(
        rf"specified:\s*{re.escape(fake)}\s+got:\s*({sha256})",
        result.stderr,
    )
    if result.returncode == 0 or len(got) != 1:
        raise RuntimeError(f"{package}: expected one hash mismatch:\n{result.stderr}")
    updates[path] = (original.replace(old[0], got[0], 1), package, got[0])

for path, (updated, package, hash_) in updates.items():
    if path.read_text() != updated:
        path.write_text(updated)
    print(f"{package}: {hash_}")
