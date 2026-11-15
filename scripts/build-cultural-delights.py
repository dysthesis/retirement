#!/usr/bin/env python3
"""Namespace Cultural Delights' fuel hook; Sophisticated Core adds getBurnTime to every Item.

Rebuild the pinned private jar, then refresh Packwiz and Nix hashes separately.
Only the interface, its override and its caller change; fuel values stay intact.
"""
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

URL = "https://cdn.modrinth.com/data/YttyNOFA/versions/gXrTmFt0/culturaldelights-1.21.1-0.19.8-refabricated.jar"
SHA512 = "b3fd084415c0b884f54ce23f9a6cd2d71627013eb55933b3c502c6dede78177f4a106d32533fd225b93ba2807069816ca308a6deb92d1f6d2de190407a1f78fb"
CLASSES = {
    "com/baisylia/culturaldelights/block/ModBlocks$9.class",
    "com/baisylia/culturaldelights/refabricated/CulturalDelightsRefabricated.class",
    "com/baisylia/culturaldelights/refabricated/util/Flammable.class",
}


def utf8_constant(text):
    value = text.encode("ascii")
    return b"\x01" + len(value).to_bytes(2, "big") + value


with urllib.request.urlopen(URL, timeout=60) as response:
    original = response.read()
if hashlib.sha512(original).hexdigest() != SHA512:
    raise ValueError("Upstream artifact changed")
old = utf8_constant("getBurnTime")
new = utf8_constant("culturaldelights$getBurnTime")
output = io.BytesIO()
with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(output, "w") as target:
    callers = {name for name in source.namelist() if name.endswith(".class") and old in source.read(name)}
    assert callers == CLASSES, f"Unexpected fuel-hook callers: {callers}"
    for entry in source.infolist():
        data = source.read(entry)
        if entry.filename in CLASSES:
            assert data.count(old) == 1, entry.filename
            data = data.replace(old, new)
        elif entry.filename == "fabric.mod.json":
            old_version = b'"version":"0.19.8-refabricated"'
            assert data.count(old_version) == 1
            data = data.replace(old_version, b'"version":"0.19.8-refabricated+retirement.1"')
        target.writestr(entry, data)
path = Path(__file__).resolve().parents[1] / "packwiz/mods/culturaldelights-1.21.1-0.19.8-refabricated+retirement.1.jar"
path.write_bytes(output.getvalue())
print(f"{hashlib.sha256(output.getvalue()).hexdigest()}  {path.name}")
