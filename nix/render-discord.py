#!/usr/bin/env python3
"""Inject an SDLink credential into the copied Minecraft runtime TOML."""

import json
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path


CONFIG = Path("config/simple-discord-link/simple-discord-link.toml")
CREDENTIAL = "discord-bot-token"


def replace_setting(text: str, name: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^([ \t]*{re.escape(name)}[ \t]*=[ \t]*).*$")
    updated, count = pattern.subn(lambda match: match[1] + json.dumps(value), text)
    if count != 1:
        raise ValueError(f"expected exactly one {name} assignment, found {count}")
    return updated


def main() -> None:
    if len(sys.argv) != 2 or re.fullmatch(r"[0-9]{17,20}", sys.argv[1]) is None:
        raise ValueError("expected one numeric Discord channel ID (17–20 digits)")

    credentials_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not credentials_dir:
        raise ValueError("systemd credentials are unavailable")

    token = (Path(credentials_dir) / CREDENTIAL).read_text(encoding="utf-8")
    token = token.rstrip("\r\n")
    if (
        not token
        or not token.isascii()
        or any(ord(char) < 33 or ord(char) > 126 for char in token)
    ):
        raise ValueError("Discord token must be a non-empty, single-line ASCII value")

    original = CONFIG.read_text(encoding="utf-8")
    before = tomllib.loads(original)
    if "botToken" not in before.get("botConfig", {}):
        raise ValueError("SDLink botConfig.botToken is missing")
    if "chatChannelID" not in before.get("channelsAndWebhooks", {}).get("channels", {}):
        raise ValueError("SDLink channelsAndWebhooks.channels.chatChannelID is missing")

    updated = replace_setting(original, "botToken", token)
    updated = replace_setting(updated, "chatChannelID", sys.argv[1])
    after = tomllib.loads(updated)
    if after["botConfig"]["botToken"] != token:
        raise ValueError("SDLink bot token substitution failed")
    if after["channelsAndWebhooks"]["channels"]["chatChannelID"] != sys.argv[1]:
        raise ValueError("SDLink channel ID substitution failed")

    # The live configuration must not be readable by other local users.
    # The temporary file is created in the destination directory for atomic rename.
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix=".sdlink-", dir=CONFIG.parent)
        temporary = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(updated)
        os.chmod(temporary, 0o600)
        os.replace(temporary, CONFIG)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"SDLink runtime configuration failed: {error}", file=sys.stderr)
        sys.exit(1)
