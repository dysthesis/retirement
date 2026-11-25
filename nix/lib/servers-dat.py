"""Write a Minecraft servers.dat: a big-endian named binary tag (NBT) compound."""

import json
import struct
import sys
from pathlib import Path


def utf(value):
    encoded = value.encode("utf-8")
    assert len(encoded) <= 65535
    return struct.pack(">H", len(encoded)) + encoded


servers = json.loads(Path(sys.argv[1]).read_text())
data = b"\x0a" + utf("")  # Root TAG_Compound
data += b"\x09" + utf("servers")  # TAG_List
data += b"\x0a" + struct.pack(">i", len(servers))  # TAG_Compound entries
for server in servers:
    for key in ("name", "ip"):
        data += b"\x08" + utf(key) + utf(server[key])
    data += b"\x00"  # End server compound
data += b"\x00"  # End root compound
out = Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(data)
