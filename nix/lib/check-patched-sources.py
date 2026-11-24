"""Check the generated Packwiz graph without fetching any remote mods."""
import hashlib
import sys
import tomllib
from pathlib import Path

old_root, new_root = map(Path, sys.argv[1:])

def read(root):
    pack = tomllib.loads((root / "pack.toml").read_text())
    index_path = root / pack["index"]["file"]
    assert hashlib.sha256(index_path.read_bytes()).hexdigest() == pack["index"]["hash"]
    index = tomllib.loads(index_path.read_text())
    entries = {entry["file"]: entry for entry in index["files"]}
    assert len(entries) == len(index["files"])
    for path, entry in entries.items():
        with (root / path).open("rb") as stream:
            assert hashlib.file_digest(stream, entry.get("hash-format", index["hash-format"])).hexdigest() == entry["hash"], path
    assert {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} == set(entries) | {"pack.toml", pack["index"]["file"]}
    return pack, entries

old, before = read(old_root)
new, after = read(new_root)
replacements = {
    "mods/voxy-1.1.0+retirement.3+neoforge.jar": "mods/voxy-1.1.0+retirement.4+neoforge.jar",
    "mods/create.pw.toml": "mods/create-1.21.1-6.0.10-retirement-panel.jar",
}
for original, replacement in replacements.items():
    del before[original]
    assert not (old_root / replacement).exists()
    assert not (new_root / original).exists()
    assert (new_root / replacement).read_bytes() == b"retirement fixture, not a Minecraft mod\n"
    assert not after.pop(replacement).get("metafile", False)
assert before == after
assert new["options"]["client-only-overrides"] == [replacements.get(p, p) for p in old["options"]["client-only-overrides"]]
assert replacements["mods/create.pw.toml"] not in new["options"]["client-only-overrides"]
old["index"]["hash"] = new["index"]["hash"]
old["options"]["client-only-overrides"] = new["options"]["client-only-overrides"]
assert old == new
print("Verified patched Packwiz hash chain, replacements and client-only scope")
