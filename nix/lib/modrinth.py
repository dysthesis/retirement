import hashlib
import json
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

downloads_file, cache_dir, output = sys.argv[1:]
cache = Path(cache_dir)
cache.mkdir()

pack = tomllib.loads(Path("pack.toml").read_text())
index = tomllib.loads(Path(pack["index"]["file"]).read_text())
client_only = set(pack.get("options", {}).get("client-only-overrides", []))
allowed_hosts = {
    "cdn.modrinth.com",
    "github.com",
    "raw.githubusercontent.com",
    "gitlab.com",
}

cache_hashes = {name: [] for name in ("sha1", "sha256", "sha512", "length-bytes")}
expected_manifest = []
expected_overrides = {}

for entry in index["files"]:
    if not entry.get("metafile", False):
        prefix = "client-overrides" if entry["file"] in client_only else "overrides"
        expected_overrides[f"{prefix}/{entry['file']}"] = (
            entry.get("hash-format", index["hash-format"]),
            entry["hash"],
        )

for entry in json.loads(Path(downloads_file).read_text()):
    path = Path(entry["file"])
    original = path.read_text()
    mod = tomllib.loads(original)
    download = mod["download"]
    mode = download.get("mode") or "url"
    hashes = json.loads(Path(entry["hashes"]).read_text())
    assert hashes[download["hash-format"]] == download["hash"].lower(), path

    cached_file = cache / hashes["sha256"][:2] / hashes["sha256"][2:]
    cached_file.parent.mkdir(exist_ok=True)
    if not cached_file.exists():
        cached_file.symlink_to(entry["source"])

    for name, values in cache_hashes.items():
        values.append(hashes[name])

    # Include server-only mods in the private client export, as before.
    updated = re.sub(r"""(?m)^[ \t]*side\s*=\s*(['"])server\1""", 'side = "both"', original)

    # ForgeCDN files remain embedded; their verified URLs avoid the metadata API.
    if mode == "metadata:curseforge":
        updated = re.sub(
            r"""(?m)^[ \t]*mode\s*=\s*(['"])metadata:curseforge\1""",
            lambda _: f"url = {json.dumps(entry['url'])}",
            updated,
        )

    rewritten = tomllib.loads(updated)
    assert rewritten.get("side") != "server", path
    assert rewritten["download"].get("mode", "url") in ("", "url"), path
    path.write_text(updated)

    destination = str(path.parent / mod["filename"])
    side = rewritten.get("side", "both")
    direct = mode == "url" and urlsplit(download["url"]).netloc in allowed_hosts

    if direct:
        requirement = (
            "optional" if mod.get("option", {}).get("optional", False) else "required"
        )
        expected_manifest.append(
            {
                "path": destination,
                "hashes": {name: hashes[name] for name in ("sha1", "sha512")},
                "env": {
                    "client": requirement,
                    "server": "unsupported" if side == "client" else requirement,
                },
                "fileSize": int(hashes["length-bytes"]),
            }
        )
    else:
        prefix = "client-overrides" if side == "client" else "overrides"
        expected_overrides[f"{prefix}/{destination}"] = (
            download["hash-format"],
            download["hash"],
        )

(cache / "index.json").write_text(json.dumps({"Version": 2, "Hashes": cache_hashes}))

subprocess.run(
    [
        "packwiz",
        "--cache",
        str(cache),
        "modrinth",
        "export",
        "--restrictDomains=true",
        "--output",
        output,
    ],
    check=True,
)

# Packwiz can report individual export failures without a failing exit status.
with zipfile.ZipFile(output) as archive:
    expected_names = set(expected_overrides) | {"overrides/", "modrinth.index.json"}
    assert set(archive.namelist()) == expected_names
    assert len(archive.namelist()) == len(expected_names)

    manifest = json.loads(archive.read("modrinth.index.json"))
    # URL re-encoding belongs to Packwiz; check payloads independently of it.
    for entry in manifest["files"]:
        del entry["downloads"]

    assert manifest["files"] == sorted(
        expected_manifest, key=lambda entry: entry["path"]
    )

    for name, (algorithm, expected_hash) in expected_overrides.items():
        with archive.open(name) as source:
            assert (
                hashlib.file_digest(source, algorithm).hexdigest()
                == expected_hash.lower()
            ), name
