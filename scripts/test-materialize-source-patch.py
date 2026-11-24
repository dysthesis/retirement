#!/usr/bin/env python3
"""Regression tests for the pinned source patch materializer, no network needed."""
import importlib.util
import random
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('materializer', HERE / 'materialize-source-patch.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def nonblank(lines):
    return [line for line in lines if line.strip()]


class MaterializeTests(unittest.TestCase):
    def test_pinned_hunks_with_missing_and_extra_blank_lines(self):
        for patchname in ('voxy-memory.patch', 'create-panel-render-only.patch', 'create-panel-reproducible.patch'):
            patch = (HERE / patchname).read_text()
            for seed in range(8):
                with self.subTest(patch=patchname, seed=seed), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    rng = random.Random(seed)
                    expected = {}
                    originals = {}
                    subprocess.run(['git', 'init', '--quiet'], cwd=root, check=True)
                    for name, hunks in M.parse(patch).items():
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        old, new = [], []
                        for i, body in enumerate(hunks):
                            sentinel = f'// untouched fixture separator {i}\n'
                            old.append(sentinel)
                            new.append(sentinel)
                            for tag, line in body:
                                if tag != '+' and line.strip():
                                    old.extend(['\n'] * rng.randrange(3))
                                    old.append(line)
                                if tag != '-' and line.strip():
                                    new.append(line)
                        old.append('// untouched final line\n')
                        new.append('// untouched final line\n')
                        # Exercise LF, CRLF, mixed line endings and no final newline.
                        endings = ['\n'] if seed % 4 == 0 else ['\r\n'] if seed % 4 == 1 else ['\n', '\r\n']
                        original = ''.join(line.removesuffix('\n') + rng.choice(endings) for line in old)
                        if seed % 4 == 3:
                            original = original.removesuffix('\n').removesuffix('\r')
                        originals[name] = original.encode()
                        path.write_bytes(originals[name])
                        expected[name] = new
                    diff = M.generate(root, patch)
                    for options in (['--check'], [], ['--reverse', '--check']):
                        subprocess.run(['git', 'apply', '--whitespace=nowarn', *options, '-'],
                                       cwd=root, input=diff, check=True)
                    for name, lines in expected.items():
                        self.assertEqual([line.rstrip('\n') for line in nonblank((root/name).read_text().splitlines(True))],
                                         [line.rstrip('\n') for line in lines])
                    subprocess.run(['git', 'apply', '--whitespace=nowarn', '--reverse', '-'],
                                   cwd=root, input=diff, check=True)
                    for name, original in originals.items():
                        self.assertEqual((root/name).read_bytes(), original)

    def test_reject_wrong_or_ambiguous_code(self):
        body = [(' ', 'start\n'), ('-', 'old\n'), ('+', 'new\n'), (' ', 'end\n')]
        with self.assertRaisesRegex(ValueError, '0 exact'):
            M.materialize('test', 'start\nchanged\nend\n', [body])
        with self.assertRaisesRegex(ValueError, '2 exact'):
            M.materialize('test', 'start\nold\nend\nstart\nold\nend\n', [body])
        with self.assertRaisesRegex(ValueError, '0 exact'):
            M.materialize('test', 'start\n old\nend\n', [body])
        self.assertEqual(M.materialize('test', 'start\n\nold\n\nend\n', [body]),
                         ['start\n', '\n', 'new\n', '\n', 'end\n'])

    def test_preserve_existing_line_endings(self):
        body = [(' ', 'start\n'), ('-', 'old\n'), ('+', 'new\n'), (' ', 'end\n')]
        self.assertEqual(M.materialize('test', 'start\r\nold\nend', [body]),
                         ['start\r\n', 'new\n', 'end'])

    def test_reject_path_traversal(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            M.parse('diff --git a/src/main/java/../../X.java b/src/main/java/../../X.java\n')


if __name__ == '__main__':
    unittest.main()
