import io
import json
import struct
import sys
import tomllib
import zipfile
from pathlib import Path
from PyQt6.QtCore import QSettings

# Prism parses instance.cfg with QSettings. Commas in JVM arguments must survive it.
archive_path, pack_path, domain, jvm_args = sys.argv[1:]
pack = tomllib.loads(Path(pack_path).read_text())
with zipfile.ZipFile(archive_path) as archive:
    names = set(archive.namelist())
    assert {
        "instance.cfg",
        "mmc-pack.json",
        "minecraft/servers.dat",
        "minecraft/packwiz-installer-bootstrap.jar",
    } <= names
    components = json.loads(archive.read("mmc-pack.json"))["components"]
    assert [(c["uid"], c["version"]) for c in components] == [
        ("net.minecraft", pack["versions"]["minecraft"]),
        ("net.neoforged", pack["versions"]["neoforge"]),
    ]
    cfg = archive.read("instance.cfg").decode()
    assert f"-s client https://{domain}/modpack/pack.toml" in cfg
    assert "OverrideJavaArgs=true" in cfg and "OverrideMemory=true" in cfg
    settings = QSettings(archive.extract("instance.cfg"), QSettings.Format.IniFormat)
    assert (
        settings.value("MaxMemAlloc") == "12288"
        and settings.value("MinMemAlloc") == "4096"
    )
    assert settings.value("JvmArgs") == jvm_args
    # Verify the embedded JAR is a nonempty ZIP archive.
    with zipfile.ZipFile(
        io.BytesIO(archive.read("minecraft/packwiz-installer-bootstrap.jar"))
    ) as jar:
        assert jar.namelist()
    data = io.BytesIO(archive.read("minecraft/servers.dat"))

    def utf():
        length = struct.unpack(">H", data.read(2))[0]
        return data.read(length).decode("utf-8")

    assert data.read(1) == b"\x0a" and utf() == ""
    assert data.read(1) == b"\x09" and utf() == "servers"
    assert data.read(1) == b"\x0a" and struct.unpack(">i", data.read(4))[0] == 1
    assert data.read(1) == b"\x08" and utf() == "name" and utf() == "Retirement Home"
    assert data.read(1) == b"\x08" and utf() == "ip" and utf() == domain
    assert data.read() == b"\x00\x00"
