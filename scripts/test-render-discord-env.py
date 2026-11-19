#!/usr/bin/env python3
"""Verify runtime SDLink rendering without starting Minecraft."""

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
FAKE_TOKEN = "fake.discord.token"


class DiscordEnvRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "config/simple-discord-link/simple-discord-link.toml"
        self.config.parent.mkdir(parents=True)
        shutil.copyfile(TEMPLATE, self.config)
        credential_dir = self.root / "credentials"
        credential_dir.mkdir()
        self.credential = credential_dir / "discord-env"
        self.credential.write_text(
            f"DISCORD_BOT_TOKEN={FAKE_TOKEN}\nDISCORD_CHANNEL_ID={CHANNEL}\n",
            encoding="utf-8",
        )
        self.environment = {**os.environ, "CREDENTIALS_DIRECTORY": str(credential_dir)}

    def run_renderer(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RENDERER)],
            cwd=self.root,
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def fails_without_modifying_config(self) -> None:
        previous = self.config.read_bytes()
        result = self.run_renderer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(previous, self.config.read_bytes())
        self.assertNotIn(FAKE_TOKEN, result.stdout + result.stderr)

    def test_renders_into_runtime_config(self) -> None:
        source = TEMPLATE.read_bytes()
        result = self.run_renderer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        parsed = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(parsed["botConfig"]["botToken"], FAKE_TOKEN)
        self.assertEqual(
            parsed["channelsAndWebhooks"]["channels"]["chatChannelID"], CHANNEL
        )
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.assertEqual(TEMPLATE.read_bytes(), source)

    def test_renders_twice(self) -> None:
        self.assertEqual(self.run_renderer().returncode, 0)
        self.assertEqual(self.run_renderer().returncode, 0)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)

    def test_missing_credential_directory(self) -> None:
        self.environment.pop("CREDENTIALS_DIRECTORY")
        self.fails_without_modifying_config()

    def test_missing_credential_file(self) -> None:
        self.credential.unlink()
        self.fails_without_modifying_config()

    def test_invalid_credential_contents(self) -> None:
        variants = [
            "",
            f"DISCORD_BOT_TOKEN={FAKE_TOKEN}\n",
            f"DISCORD_CHANNEL_ID={CHANNEL}\n",
            (
                f"DISCORD_BOT_TOKEN={FAKE_TOKEN}\n"
                f"DISCORD_CHANNEL_ID={CHANNEL}\nOTHER=bad\n"
            ),
            (
                f"DISCORD_BOT_TOKEN={FAKE_TOKEN}\n"
                f"DISCORD_CHANNEL_ID={CHANNEL}\nDISCORD_CHANNEL_ID={CHANNEL}\n"
            ),
            f'DISCORD_BOT_TOKEN="{FAKE_TOKEN}"\nDISCORD_CHANNEL_ID={CHANNEL}\n',
            f"DISCORD_BOT_TOKEN=hello world\nDISCORD_CHANNEL_ID={CHANNEL}\n",
            f"DISCORD_BOT_TOKEN={FAKE_TOKEN}\nDISCORD_CHANNEL_ID=NOT_AN_ID\n",
            (
                f"DISCORD_BOT_TOKEN={FAKE_TOKEN}\n"
                f"DISCORD_CHANNEL_ID={CHANNEL}\nDISCORD_BOT_TOKEN={FAKE_TOKEN}\n"
            ),
        ]
        for contents in variants:
            with self.subTest(contents=contents):
                self.credential.write_text(contents, encoding="utf-8")
                self.fails_without_modifying_config()

    def test_rejects_duplicate_toml_keys(self) -> None:
        self.config.write_text(
            self.config.read_text(encoding="utf-8")
            + '\n[other]\nbotToken = "shadow"\n',
            encoding="utf-8",
        )
        self.fails_without_modifying_config()


if __name__ == "__main__":
    unittest.main()
