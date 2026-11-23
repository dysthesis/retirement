#!/usr/bin/env python3
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location('factory', Path(__file__).with_name('factory-performance.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class FactoryPerformance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'mods').mkdir()
        self.rays = self.put(M.RAYS, b'# comment\r\nenabled=true\r\nenvironment_evaluation_ray_count=32\r\nenvironment_evaluation_ray_bounces=4\r\nunsafe_level_access=false\r\n')
        self.rates = self.put(M.RATES, b'# rates\ncreate\\:steam=-1\nminecraft\\:block.candle.extinguish=-1\nminecraft\\:weather.rain=0\n')
        self.map = self.put(M.MAP, b'biome_blending = false\nmap_writing_distance = -1\nupdate_chunks = true\n')
        self.buffer = self.put(M.BUFFER, b'{"fast_buffer_upload":true,"hud_batching":true,"other":{"number":3}}\n')

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def plan(self, *args):
        return M.plan(self.root, M.parser().parse_args([str(self.root), *args]))

    def apply(self, edits):
        with contextlib.redirect_stdout(io.StringIO()):
            M.apply(edits)

    def test_rays_preview_and_backup(self):
        old = self.rays.read_bytes()
        edits = self.plan('--acoustic-rays')
        self.assertEqual(self.rays.read_bytes(), old)
        self.apply(edits)
        self.assertEqual(self.rays.read_bytes(), old.replace(b'count=32', b'count=16').replace(b'bounces=4', b'bounces=2'))
        self.assertEqual(list(self.rays.parent.glob(self.rays.name + '.retirement-backup-*'))[0].read_bytes(), old)
        self.assertEqual(self.plan('--acoustic-rays'), [])

    def test_boiler_only(self):
        old = self.rates.read_bytes()
        self.apply(self.plan('--boiler-limit', '0'))
        self.assertEqual(self.rates.read_bytes(), old.replace(b'=-1', b'=0'))
        self.apply(self.plan('--boiler-limit', '2'))
        self.assertIn(b'create\\:steam=2', self.rates.read_bytes())
        self.assertIn(b'minecraft\\:weather.rain=0', self.rates.read_bytes())
        self.assertEqual(len(list(self.rates.parent.glob(self.rates.name + '.retirement-backup-*'))), 2)

    def test_sound_disable_only(self):
        old = self.rays.read_bytes()
        self.apply(self.plan('--sound-physics', 'off'))
        self.assertEqual(self.rays.read_bytes(), old.replace(b'enabled=true', b'enabled=false'))

    def test_map_independent(self):
        old = self.map.read_bytes()
        self.apply(self.plan('--map-distance', '8'))
        self.assertEqual(self.map.read_bytes(), old.replace(b'= -1', b'= 8'))
        self.apply(self.plan('--map-updates-off'))
        self.assertIn(b'update_chunks = false', self.map.read_bytes())

    def test_buffer_preserves_other_settings(self):
        self.apply(self.plan('--buffer-upload-off'))
        self.assertEqual(json.loads(self.buffer.read_bytes()), {'fast_buffer_upload': False, 'hud_batching': True, 'other': {'number': 3}})
        self.assertEqual(self.plan('--buffer-upload-off'), [])

    def test_duplicate_rejected(self):
        self.rates.write_bytes(self.rates.read_bytes() + b'create\\:steam=4\n')
        with self.assertRaises(ValueError):
            self.plan('--boiler-limit', '0')

    def test_unescaped_colon_rejected(self):
        self.rates.write_bytes(b'create:steam=-1\n')
        with self.assertRaises(ValueError):
            self.plan('--boiler-limit', '0')

    def test_continuation_rejected(self):
        with self.assertRaises(ValueError):
            M.properties(b'other=continued\\\nkey=1\n', {'key': '2'})

    def test_missing_key_no_changes(self):
        self.rates.write_bytes(b'create\\:steam=-1\n')
        old = self.rays.read_bytes()
        with self.assertRaises(ValueError):
            self.plan('--acoustic-rays', '--boiler-limit', '0')
        self.assertEqual(self.rays.read_bytes(), old)

    def test_preflight_no_partial_write(self):
        old = self.rays.read_bytes()
        edits = self.plan('--acoustic-rays', '--boiler-limit', '0')
        self.rates.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.apply(edits)
        self.assertEqual(self.rays.read_bytes(), old)

    def test_symlink_rejected(self):
        real = self.rays.with_name('actual.properties')
        self.rays.rename(real)
        self.rays.symlink_to(real)
        with self.assertRaises(ValueError):
            self.plan('--acoustic-rays')

    def test_duplicate_json_rejected(self):
        self.buffer.write_bytes(b'{"fast_buffer_upload":true,"fast_buffer_upload":false}')
        with self.assertRaises(ValueError):
            self.plan('--buffer-upload-off')

    def test_photon_verified_fixture(self):
        archive = self.root / 'shaderpacks' / M.PHOTON
        archive.parent.mkdir()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('shaders/settings.glsl', 'const float shadowDistance = 128.0; // [64.0 96.0 128.0]\n')
        digest = hashlib.sha512(archive.read_bytes()).hexdigest()
        sidecar = archive.with_name(archive.name + '.txt')
        with self.assertRaises(ValueError):
            self.plan('--photon-shadow-distance', '64')
        # A fixture is not the actual pinned shader. Replace only its expected hash.
        with patch.object(M, 'PHOTON_HASH', digest):
            with self.assertRaises(ValueError):
                self.plan('--photon-shadow-distance', '80')
            self.apply(self.plan('--photon-shadow-distance', '64'))
            self.assertEqual(sidecar.read_bytes(), b'shadowDistance=64.0\n')
            sidecar.write_bytes(b'shadowDistance=64.0\nOTHER=true\n')
            self.apply(self.plan('--photon-shadow-distance', '96'))
            self.assertEqual(sidecar.read_bytes(), b'shadowDistance=96.0\nOTHER=true\n')


if __name__ == '__main__':
    unittest.main()
