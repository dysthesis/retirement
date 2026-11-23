#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("client-performance.py")


class ClientPerformanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.instance = Path(self.temp.name)
        self.config = self.instance / "config"
        self.config.mkdir()
        self.voxy = self.config / "voxy-config.json"
        self.emf = self.config / "entity_model_features.json"
        self.voxy.write_text('{"section_render_distance": 16, "service_threads": 7, "color_fix": true}\n')
        self.emf.write_text('{"animationLODDistance": 20, "retainDetailOnLowFps": true, "custom": [1, 2]}\n')

    def invoke(self, *args, check=True):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.instance), *args],
                              check=check, capture_output=True, text=True)

    def test_preview_and_apply(self):
        before = {p: p.read_bytes() for p in (self.voxy, self.emf)}
        self.invoke()
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.invoke("--apply")
        self.assertEqual(json.loads(self.voxy.read_text()),
                         {"section_render_distance": 8, "service_threads": 7, "color_fix": True})
        self.assertEqual(json.loads(self.emf.read_text()),
                         {"animationLODDistance": 16, "retainDetailOnLowFps": False, "custom": [1, 2]})
        for path, original in before.items():
            backups = list(self.config.glob(path.name + ".retirement-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
        self.invoke("--apply")
        self.assertEqual(len(list(self.config.glob("*.retirement-backup-*"))), 2)

    def test_selection(self):
        before = self.emf.read_bytes()
        self.invoke("--component", "voxy", "--apply")
        self.assertEqual(self.emf.read_bytes(), before)
        self.assertEqual(json.loads(self.voxy.read_text())["section_render_distance"], 8)

    def test_invalid_second_config_does_not_modify_first(self):
        before = self.voxy.read_bytes()
        self.emf.write_text('{"animationLODDistance": 20, "animationLODDistance": 0}')
        self.assertNotEqual(self.invoke("--apply", check=False).returncode, 0)
        self.assertEqual(self.voxy.read_bytes(), before)
        self.assertFalse(list(self.config.glob("*.retirement-backup-*")))

    def test_missing_config(self):
        self.emf.unlink()
        before = self.voxy.read_bytes()
        self.assertNotEqual(self.invoke("--apply", check=False).returncode, 0)
        self.assertEqual(self.voxy.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
