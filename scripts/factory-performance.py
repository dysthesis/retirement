#!/usr/bin/env python3
"""Preview or apply independent factory-performance experiments to a stopped client."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

SPR = 'config/sound_physics_remastered/'
RAYS = SPR + 'soundphysics.properties'
RATES = SPR + 'sound_rates.properties'
MAP = 'config/xaero/world-map/profiles/default.cfg'
BUFFER = 'config/immediatelyfast.json'
PHOTON = 'photon_v1.4.zip'
PHOTON_HASH = ('2dec87084dccf91a72a06235ecbfb3627f066699b5f70583f06077cba61433aedbfa'
               '6af28eb68bf1cdc726149cc3d9a587517cfab59e6a24e9d6a40b6874d655')
# These files are generated with simple single-line assignments. Reject unfamiliar
# syntax rather than silently interpreting arbitrary Java properties or Xaero files.
ASSIGN = re.compile(rb'([ \t]*)([A-Za-z0-9_./-]+(?:\\:[A-Za-z0-9_./-]+)?)([ \t]*=[ \t]*)([^\r\n]*)(\r\n|\n|\r|$)')


def properties(data, updates, *, add=False):
    lines = data.splitlines(keepends=True)
    seen = {}
    changes = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith((b'#', b'!')):
            continue
        raw = line.rstrip(b'\r\n')
        if (len(raw) - len(raw.rstrip(b'\\'))) % 2:
            raise ValueError(f'Unsupported continued assignment on line {i + 1}')
        match = ASSIGN.fullmatch(line)
        if not match:
            raise ValueError(f'Unsupported assignment on line {i + 1}; use the mod GUI')
        key = match[2].decode('ascii').replace(r'\:', ':')
        if key in seen:
            raise ValueError(f'Duplicate assignment: {key}')
        seen[key] = i
        if key not in updates:
            continue
        old = match[4].decode('ascii')
        new = updates[key]
        if old != new:
            lines[i] = match[1] + match[2] + match[3] + new.encode('ascii') + match[5]
            changes[key] = (old, new)
    missing = updates.keys() - seen.keys()
    if missing and not add:
        raise ValueError(f'Missing generated settings: {", ".join(sorted(missing))}; use the mod GUI')
    newline = b'\r\n' if b'\r\n' in data else b'\n'
    for key in sorted(missing):
        if lines and not lines[-1].endswith((b'\n', b'\r')):
            lines[-1] += newline
        lines.append(key.replace(':', r'\:').encode('ascii') + b'=' + updates[key].encode('ascii') + newline)
        changes[key] = ('<absent>', updates[key])
    return b''.join(lines), changes


def json_object(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f'Invalid JSON constant: {value}')
    obj = json.loads(data, object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(obj, dict):
        raise ValueError('Expected JSON object')
    return obj


def buffer_off(data):
    obj = json_object(data)
    old = obj.get('fast_buffer_upload')
    if type(old) is not bool:
        raise ValueError('No generated boolean fast_buffer_upload option; use the mod GUI')
    if not old:
        return data, {}
    obj['fast_buffer_upload'] = False
    return (json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode(), {'fast_buffer_upload': (True, False)}


def checked(root, relative, missing=False):
    path = root / relative
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink():
            raise ValueError(f'Refusing symlink: {item}')
    if not path.parent.is_dir() or (not path.is_file() and not (missing and not path.exists())):
        raise ValueError(f'Expected generated file: {path}; launch once first')
    return path


def photon_check(root, distance):
    # A sidecar is only meaningful for this exact shader archive. Do not guess
    # option names for other shader packs or for newer Photon releases.
    archive = checked(root, 'shaderpacks/' + PHOTON)
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha512').hexdigest()
    if digest != PHOTON_HASH:
        raise ValueError('Photon archive hash differs from the pinned pack; use shader options instead')
    with zipfile.ZipFile(archive) as z:
        candidates = [n for n in z.namelist() if n.endswith('shaders/settings.glsl')]
        if len(candidates) != 1:
            raise ValueError('Cannot locate a unique Photon settings.glsl')
        source = z.read(candidates[0]).decode('utf-8')
    match = re.search(r'^\s*const\s+float\s+shadowDistance\s*=\s*[\d.]+\s*;\s*//\s*\[([^\]]+)\]', source, re.M)
    if not match or f'{distance}.0' not in match[1].split():
        raise ValueError('Requested shadow distance not found in pinned shader options; use shader GUI')
    return 'shaderpacks/' + PHOTON + '.txt'


def plan(root, args):
    updates = {}
    if args.acoustic_rays:
        updates.setdefault(RAYS, {}).update(environment_evaluation_ray_count='16', environment_evaluation_ray_bounces='2')
    if args.sound_physics is not None:
        updates.setdefault(RAYS, {})['enabled'] = 'true' if args.sound_physics == 'on' else 'false'
    if args.boiler_limit is not None:
        updates[RATES] = {key: str(args.boiler_limit) for key in ('create:steam', 'minecraft:block.candle.extinguish')}
    if args.map_distance is not None:
        updates.setdefault(MAP, {})['map_writing_distance'] = str(args.map_distance)
    if args.map_updates_off:
        updates.setdefault(MAP, {})['update_chunks'] = 'false'
    sidecar = None
    if args.photon_shadow_distance is not None:
        sidecar = photon_check(root, args.photon_shadow_distance)
        updates[sidecar] = {'shadowDistance': f'{args.photon_shadow_distance}.0'}
    edits = []
    for relative, settings in updates.items():
        path = checked(root, relative, missing=relative == sidecar)
        original = path.read_bytes() if path.exists() else None
        revised, changes = properties(original or b'', settings, add=relative == sidecar)
        if changes:
            edits.append((path, original, revised, changes))
    if args.buffer_upload_off:
        path = checked(root, BUFFER)
        original = path.read_bytes()
        revised, changes = buffer_off(original)
        if changes:
            edits.append((path, original, revised, changes))
    return edits


def apply(edits):
    # Preflight every file before changing any. Individual replacements are atomic;
    # the operation is not a transaction across multiple files.
    for path, original, _, _ in edits:
        if path.is_symlink() or (path.read_bytes() if path.exists() else None) != original:
            raise ValueError(f'File changed since preview: {path}')
    for path, original, revised, _ in edits:
        backup = None
        if original is not None:
            fd, backup = tempfile.mkstemp(prefix=path.name + '.retirement-backup-', dir=path.parent)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(original)
            shutil.copymode(path, backup)
        fd, tmp = tempfile.mkstemp(prefix='.retirement-config-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(revised)
                handle.flush()
                os.fsync(handle.fileno())
            if original is not None:
                shutil.copymode(path, tmp)
                os.replace(tmp, path)
            else:
                # Exclusive publication of a new sidecar; never overwrite a file
                # that appeared after the preflight.
                os.link(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        print(f'Updated {path}; backup: {backup or "none (new file)"}')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('instance', type=Path, help='Minecraft game directory containing config/ and mods/')
    p.add_argument('--acoustic-rays', action='store_true', help='16 initial rays, 2 bounces')
    p.add_argument('--sound-physics', choices=('on', 'off'), help='diagnostic: enable/disable acoustic effects')
    p.add_argument('--boiler-limit', type=int, choices=(-1, 0, 1, 2, 4), help='per sound per tick: -1 unlimited, 0 bypass, 2 initial deployment candidate')
    p.add_argument('--map-distance', type=int, choices=(6, 8, 12, 16), help='experimental map writing radius (active default profile only)')
    p.add_argument('--map-updates-off', action='store_true', help='experimental; previously mapped chunks can become stale')
    p.add_argument('--buffer-upload-off', action='store_true', help='experimental ImmediatelyFast workaround')
    p.add_argument('--photon-shadow-distance', type=int, choices=(64, 80, 96, 112, 128), help='Photon v1.4 only; confirm this shader is active')
    p.add_argument('--apply', action='store_true', help='write changes; default is preview')
    return p


def main():
    p = parser()
    args = p.parse_args()
    if not any((args.acoustic_rays, args.sound_physics is not None, args.boiler_limit is not None,
                args.map_distance is not None, args.map_updates_off, args.buffer_upload_off,
                args.photon_shadow_distance is not None)):
        p.error('Select at least one explicit experiment')
    root = args.instance.resolve()
    if not (root / 'config').is_dir() or not (root / 'mods').is_dir():
        p.error('Expected a launched Minecraft instance with config/ and mods/')
    try:
        edits = plan(root, args)
        if not edits:
            print('No changes needed.')
            return
        for path, _, _, changes in edits:
            print(path)
            for key, (old, new) in changes.items():
                print(f'  {key}: {old!r} -> {new!r}')
        if args.apply:
            apply(edits)
        else:
            print('Preview only. Close Minecraft and repeat with --apply to write.')
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        p.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
