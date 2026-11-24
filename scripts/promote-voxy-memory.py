#!/usr/bin/env python3
"""Promote a tested private Voxy build only after explicit approval and hash verification."""
import argparse
import hashlib
from pathlib import Path
import os
import re
import shutil
import tomllib
import zipfile

OLD = 'voxy-1.1.0+retirement.3+neoforge.jar'
NEW = 'voxy-1.1.0+retirement.4+neoforge.jar'
OLD_HASH = '0f2781db79bec5c5aee3e74a2f685416fb26d306f2f30ba4d9be5980498f19fd'
VERSION = '1.1.0+retirement.4+neoforge'
ROOT = Path(__file__).resolve().parent.parent
PREFIX = 'me/cortex/voxy/'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def check_jar(path):
    if path.name != NEW:
        raise ValueError(f'Expected {NEW}')
    with zipfile.ZipFile(path) as z:
        if len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('Duplicate ZIP entries')
        if z.testzip() is not None:
            raise ValueError('Invalid JAR CRC')
        mods = tomllib.loads(z.read('META-INF/neoforge.mods.toml').decode())['mods']
        if not any(m['modId'] == 'voxy' and m['version'] == VERSION for m in mods):
            raise ValueError('Unexpected Voxy version metadata')
        for cls, tokens in {
            'client/config/VoxyConfig.class': [b'nativeGeometryCacheMib', b'secondarySectionCacheLimit', b'gpuGeometryLimitMib'],
            'client/core/rendering/GeometryCache.class': [b'takeForReuse', b'debugSummary'],
            'client/core/rendering/hierachical/AsyncNodeManager.class': [b'takeForReuse', b'debugSummary'],
            'client/VoxyClientInstance.class': [b'secondaryCacheCapacity'],
            'common/world/WorldEngine.class': [b'secondaryCacheCapacity'],
            'client/core/VoxyRenderSystem.class': [b'gpuGeometryLimitMib'],
        }.items():
            data = z.read(PREFIX + cls)
            if not data.startswith(b'\xca\xfe\xba\xbe') or not all(t in data for t in tokens):
                raise ValueError(f'Missing expected change: {cls}')
    return sha(path)


def replace_override(text):
    parsed = tomllib.loads(text)
    old_path, new_path = 'mods/' + OLD, 'mods/' + NEW
    overrides = parsed['options']['client-only-overrides']
    if overrides.count(old_path) != 1 or new_path in overrides or text.count('"' + old_path + '"') != 1:
        raise ValueError('Unexpected client-only-overrides; review manually')
    new = text.replace('"' + old_path + '"', '"' + new_path + '"')
    expected = parsed | {'options': parsed['options'] | {
        'client-only-overrides': [new_path if x == old_path else x for x in overrides]}}
    if tomllib.loads(new) != expected:
        raise ValueError('Unexpected pack metadata change')
    return new


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate', type=Path)
    p.add_argument('--check-jar', action='store_true', help='Check classes and version only; no repository changes')
    p.add_argument('--repeat-build', type=Path, help='Independent rebuilt candidate; required for promotion')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    candidate = args.candidate.resolve(strict=True)
    digest = check_jar(candidate)
    print(f'{candidate.name}: {digest}')
    if args.check_jar:
        if args.apply:
            p.error('--check-jar cannot be combined with --apply')
        return
    if args.repeat_build is None:
        p.error('--repeat-build is required')
    other = args.repeat_build.resolve(strict=True)
    if other == candidate or other.samefile(candidate) or check_jar(other) != digest:
        raise ValueError('Repeat build must be separate and byte-identical')
    old = ROOT / 'packwiz/mods' / OLD
    target = old.with_name(NEW)
    pack = ROOT / 'packwiz/pack.toml'
    pin = ROOT / 'scripts/voxy-memory.sha256'
    if old.is_symlink() or not old.is_file() or sha(old) != OLD_HASH:
        raise ValueError('Original Voxy JAR differs from the researched binary')
    if target.exists() or pin.exists() or candidate == target:
        raise ValueError('Candidate or pin already exists in repository')
    original = pack.read_text()
    updated = replace_override(original)
    print(f'Replace {old.name} with {target.name}; preserve all other overrides; write {pin.name}.')
    if not args.apply:
        print('Preview only. Test candidate on client before using --apply.')
        return
    # On failure before the old JAR is removed, restore the original metadata and remove new files.
    # Keep the previous JAR recoverable in Git. This does not modify existing client installations.
    try:
        with target.open('xb') as f, candidate.open('rb') as src:
            shutil.copyfileobj(src, f)
        if sha(target) != digest:
            raise ValueError('Copied JAR failed SHA-256 verification')
        with pin.open('x') as f:
            f.write(digest + '\n')
        if pack.read_text() != original:
            raise ValueError('pack.toml changed concurrently')
        pack.write_text(updated)
        old.unlink()
    except BaseException:
        if old.exists():
            if pack.read_text() == updated:
                pack.write_text(original)
            target.unlink(missing_ok=True)
            pin.unlink(missing_ok=True)
        raise
    print('Promoted. Run just rehash; stage the deletion, new JAR, pin, and updated pack/index.')
    print('Private use only; do not publish unofficial Voxy builds.')


if __name__ == '__main__':
    main()
