#!/usr/bin/env python3
"""Test SDLink credential rendering without starting Minecraft."""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


RENDERER = Path(sys.argv[1]).resolve()
TEMPLATE = Path(sys.argv[2]).resolve()
sys.argv = [sys.argv[0]]
CHANNEL = "123456789012345678"


class RendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        config = self.root / "config/simple-discord-link/simple-discord-link.toml"
        config.parent.mkdir(parents=True)
        shutil.copyfile(TEMPLATE, config)
        self.config = config
        credentials = self.root / "credentials"
        credentials.mkdir()
        self.token = credentials / "discord-bot-token"
        self.token.write_text("fake.discord.token\n", encoding="utf-8")
        self.env = dict(os.environ, CREDENTIALS_DIRECTORY=str(credentials))

    def run_renderer(self, channel: str = CHANNEL) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RENDERER), channel],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_renders_only_runtime_file(self) -> None:
        baseline = TEMPLATE.read_bytes()
        result = self.run_renderer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("fake.discord.token", result.stderr)
        rendered = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(rendered["botConfig"]["botToken"], "fake.discord.token")
        self.assertEqual(
            rendered["channelsAndWebhooks"]["channels"]["chatChannelID"], CHANNEL
        )
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.assertEqual(TEMPLATE.read_bytes(), baseline)

    def test_fails_closed_without_credentials(self) -> None:
        self.env.pop("CREDENTIALS_DIRECTORY")
        original = self.config.read_bytes()
        result = self.run_renderer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.config.read_bytes(), original)

    def test_fails_closed_without_valid_token(self) -> None:
        for value in ("", "line1\nline2", "contains space", "\x00bad"):
            with self.subTest(value=value):
                self.token.write_text(value, encoding="utf-8")
                original = self.config.read_bytes()
                result = self.run_renderer()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.config.read_bytes(), original)

    def test_rejects_duplicate_settings(self) -> None:
        self.config.write_text(
            self.config.read_text(encoding="utf-8")
            + '\n[another]\nbotToken = "shadow"\n',
            encoding="utf-8",
        )
        original = self.config.read_bytes()
        result = self.run_renderer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.config.read_bytes(), original)

    def test_rejects_invalid_channel(self) -> None:
        original = self.config.read_bytes()
        result = self.run_renderer("NOT_A_DISCORD_CHANNEL")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
