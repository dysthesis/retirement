#!/usr/bin/env python3
"""Keep the released Small Ships payloads; replace only its native config handler and version."""
import hashlib
import sys
import zipfile

handler = "com/talhanation/smallships/neoforge/common/CommonModBus.class"
metadata = "META-INF/neoforge.mods.toml"
with zipfile.ZipFile(sys.argv[1]) as release, zipfile.ZipFile(sys.argv[2]) as compiled:
    entries = release.infolist()
    if len({entry.filename for entry in entries}) != len(entries):
        raise ValueError("Duplicate release ZIP entries")
    patched_class = compiled.read(handler)
    if hashlib.sha256(patched_class).hexdigest() != "b998169d84971a59599c0f9cbe29cc4347bc1efb6abdd8d16170aa7680907669":
        raise ValueError("Unexpected compiled config handler")
    original_metadata = release.read(metadata)
    if original_metadata.count(b'version = "2.0.2"') != 1 or b'license = "All Rights Reserved"' not in original_metadata:
        raise ValueError("Unexpected release version or license")
    replacements = {
        handler: patched_class,
        metadata: original_metadata.replace(b'version = "2.0.2"', b'version = "2.0.2+retirement.1"'),
    }
    with zipfile.ZipFile(sys.argv[3], "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for original in sorted(entries, key=lambda entry: entry.filename):
            entry = zipfile.ZipInfo(original.filename, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = original.create_system
            entry.external_attr = original.external_attr
            entry.comment = original.comment
            output.writestr(entry, replacements.get(original.filename, release.read(original.filename)), compresslevel=9)
    with zipfile.ZipFile(sys.argv[3]) as output:
        if set(output.namelist()) != {entry.filename for entry in entries}:
            raise AssertionError("Release entry set changed")
        changed = {entry.filename for entry in entries if output.read(entry.filename) != release.read(entry.filename)}
        if changed != set(replacements):
            raise AssertionError(f"Unexpected changed release payloads: {changed}")
print("PASS: patched CommonModBus SHA-256 b998169d84971a59599c0f9cbe29cc4347bc1efb6abdd8d16170aa7680907669")
print(f"PASS: all {len(entries) - 2} non-target release entries remain byte-identical; private version applied, license retained")
