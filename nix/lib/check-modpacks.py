import hashlib
import json
import sys
import tomllib
from pathlib import Path


source, client, server = map(Path, sys.argv[1:])
pack_bytes = (source / "pack.toml").read_bytes()
pack = tomllib.loads(pack_bytes.decode())
index = tomllib.loads((source / pack["index"]["file"]).read_text())
client_only = set(pack.get("options", {}).get("client-only-overrides", []))

for side, output in (("client", client), ("server", server)):
    assert (output / "pack.toml").read_bytes() == pack_bytes
    state = json.loads((output / "packwiz.json").read_text())
    assert state["cachedSide"] == side
    assert state["packFileHash"] == {"type": "sha256", "value": hashlib.sha256(pack_bytes).hexdigest()}
    assert state["indexFileHash"] == {"type": pack["index"]["hash-format"], "value": pack["index"]["hash"]}
    assert set(state["cachedFiles"]) == {entry["file"] for entry in index["files"]}

    expected_files = {"pack.toml", "packwiz.json"}

    for entry in index["files"]:
        metafile = entry.get("metafile", False)
        mod = tomllib.loads((source / entry["file"]).read_text()) if metafile else {}
        on_side = mod.get("side", "both") in ("", "both", side)
        destination = str(Path(entry["file"]).parent / mod["filename"]) if metafile else entry["file"]
        cached = state["cachedFiles"][entry["file"]]

        if not on_side:
            assert cached["onlyOtherSide"], entry["file"]
            continue

        assert cached["cachedLocation"] == destination, entry["file"]
        assert cached["hash"] == {"type": entry.get("hash-format", index["hash-format"]), "value": entry["hash"]}

        if metafile:
            assert cached["linkedFileHash"] == {"type": mod["download"]["hash-format"], "value": mod["download"]["hash"]}

        if side == "server" and destination in client_only:
            continue

        expected_files.add(destination)
        pinned = mod["download"] if metafile else entry | {"hash-format": entry.get("hash-format", index["hash-format"])}

        with (output / destination).open("rb") as installed:
            assert hashlib.file_digest(installed, pinned["hash-format"]).hexdigest() == pinned["hash"].lower(), destination

    actual_files = set()

    for path in output.rglob("*"):
        assert not path.is_symlink(), path
        if path.is_file():
            assert not path.stat().st_mode & 0o111, path
            actual_files.add(str(path.relative_to(output)))

    assert actual_files == expected_files, (side, actual_files ^ expected_files)
    print(f"{side}: verified {len(actual_files)} files and installer state")
