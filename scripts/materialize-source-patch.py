#!/usr/bin/env python3
"""Reconstruct pinned source patches using actual checkout whitespace.

Only blank lines and line endings may differ from the input hunks. All
nonblank old lines, including indentation, must match exactly once. Reject changed or ambiguous
code. Produce a normal contextual Git diff; check it before applying it.
"""
import difflib
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


def parse(text):
    lines = text.splitlines(keepends=True)
    files = {}
    i = 0
    while i < len(lines):
        header = re.fullmatch(r'diff --git a/(\S+) b/(\S+)\n', lines[i])
        if not header or header[1] != header[2]:
            raise ValueError(f'Unsupported file header: {lines[i]!r}')
        name = header[1]
        path = PurePosixPath(name)
        allowed = (name.startswith('src/main/java/') and path.suffix == '.java'
                   or name in {'gradle/java.gradle', 'gradle/wrapper/gradle-wrapper.properties'})
        if path.is_absolute() or '..' in path.parts or not allowed or name in files:
            raise ValueError(f'Unsupported or duplicate path: {name}')
        if lines[i+1:i+3] != [f'--- a/{name}\n', f'+++ b/{name}\n']:
            raise ValueError(f'Unexpected file headers: {name}')
        i += 3
        hunks = files[name] = []
        while i < len(lines) and lines[i].startswith('@@ '):
            h = re.fullmatch(r'@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@[^\n]*\n', lines[i])
            if not h:
                raise ValueError(f'Bad hunk header: {lines[i]!r}')
            i += 1
            body = []
            while i < len(lines) and lines[i][:1] in (' ', '+', '-'):
                tag, line = lines[i][0], lines[i][1:]
                if tag == '-' and not line.strip():
                    raise ValueError('Blank-line deletion is unsupported')
                body.append((tag, line))
                i += 1
            if (sum(t != '+' for t, _ in body) != int(h[1] or 1)
                    or sum(t != '-' for t, _ in body) != int(h[2] or 1)
                    or not any(t == ' ' and s.strip() for t, s in body)):
                raise ValueError(f'Invalid or unanchored hunk: {name}')
            hunks.append(body)
        if not hunks:
            raise ValueError(f'No hunks: {name}')
    if not files:
        raise ValueError('Empty source patch')
    return files


def materialize(name, original, hunks):
    lines = original.splitlines(keepends=True)
    nonblank = [(i, line) for i, line in enumerate(lines) if line.strip()]
    values = [line.removesuffix("\n").removesuffix("\r") for _, line in nonblank]
    insertions = {}
    deletions = set()
    last_end = -1
    for number, body in enumerate(hunks, 1):
        old = [(i, line) for i, (tag, line) in enumerate(body) if tag != '+' and line.strip()]
        needle = [line.removesuffix("\n") for _, line in old]
        matches = [j for j in range(len(values)-len(needle)+1)
                   if values[j:j+len(needle)] == needle]
        if len(matches) != 1:
            raise ValueError(f'{name}: hunk {number} has {len(matches)} exact nonblank matches; expected one. First anchor: {needle[0].strip()}')
        start = matches[0]
        positions = {i: nonblank[start+j][0] for j, (i, _) in enumerate(old)}
        if min(positions.values()) <= last_end:
            raise ValueError(f'{name}: overlapping or out-of-order hunk {number}')
        last_end = max(positions.values())
        i = 0
        while i < len(body):
            if body[i][0] == ' ':
                i += 1
                continue
            begin = i
            while i < len(body) and body[i][0] != ' ':
                i += 1
            removed = [positions[j] for j in range(begin, i) if body[j][0] == '-']
            added = [line for tag, line in body[begin:i] if tag == '+']
            deletions.update(removed)
            if added:
                if removed:
                    at = removed[0]
                else:
                    before = [p for j, p in positions.items() if j < begin]
                    after = [p for j, p in positions.items() if j >= i]
                    # Insert next to an exact anchor; retain existing blank lines.
                    at = before[-1]+1 if before else after[0]
                # Retain existing line endings; new lines use the adjacent style.
                anchor = lines[min(at, len(lines)-1)]
                if not anchor.endswith('\n') and at > 0:
                    anchor = lines[at-1]
                ending = '\r\n' if anchor.endswith('\r\n') else '\n'
                insertions.setdefault(at, []).extend(
                    line.removesuffix('\n') + ending for line in added)
    result = []
    for i in range(len(lines)+1):
        if i in insertions and result and not result[-1].endswith('\n'):
            ending = '\r\n' if insertions[i][0].endswith('\r\n') else '\n'
            result[-1] += ending
        result.extend(insertions.get(i, []))
        if i < len(lines) and i not in deletions:
            result.append(lines[i])
    return result


def generate(root, patch):
    chunks = []
    for name, hunks in parse(patch).items():
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Invalid source file: {name}')
        original = path.read_bytes().decode('utf-8')
        if '\r' in original.replace('\r\n', ''):
            raise ValueError(f'Unexpected source line endings: {name}')
        revised = materialize(name, original, hunks)
        diff = list(difflib.unified_diff(original.splitlines(keepends=True), revised,
                                        fromfile=f'a/{name}', tofile=f'b/{name}', n=3))
        if not diff:
            raise ValueError(f'No changes generated: {name}')
        # difflib does not emit Git's missing-final-newline marker.
        # Preserve it if the old or revised source has no terminal newline.
        for line in diff:
            if line.endswith('\n'):
                chunks.append(line)
            else:
                chunks.append(line + '\n\\ No newline at end of file\n')
    return ''.join(chunks).encode('utf-8')


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: materialize-source-patch.py CHECKOUT SOURCE_PATCH')
    root, patch = map(Path, sys.argv[1:])
    try:
        diff = generate(root, patch.read_text(encoding='utf-8'))
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
    for options in (['--check'], []):
        subprocess.run(['git', '-C', str(root), 'apply', '--whitespace=nowarn', *options, '-'],
                       input=diff, check=True)
    print(f'Applied {patch.name} with exact nonblank context and checkout-derived line positions')


if __name__ == '__main__':
    main()
