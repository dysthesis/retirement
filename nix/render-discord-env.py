#!/usr/bin/env python3
"""Render SDLink's runtime TOML from a systemd credential file.

The source Packwiz TOML is not modified. Never include secrets in exceptions.
"""

import json
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path


CONFIG = Path("config/simple-discord-link/simple-discord-link.toml")
CREDENTIAL = "discord-env"
KEYS = frozenset({"DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"})


def load_values(path: Path) -> tuple[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in KEYS or key in values:
            raise ValueError(
                "Discord credential file has an unexpected or duplicate assignment"
            )
        values[key] = value
    if values.keys() != KEYS:
        raise ValueError(
            "Discord credential file must contain both required assignments"
        )
    token = values["DISCORD_BOT_TOKEN"]
    channel_id = values["DISCORD_CHANNEL_ID"]
    # A strict subset of EnvironmentFile syntax; no shell or quote expansion.
    if re.fullmatch(r"[A-Za-z0-9._-]+", token) is None:
        raise ValueError("Discord bot token contains invalid characters")
    if re.fullmatch(r"[0-9]{17,20}", channel_id) is None:
        raise ValueError("Discord channel ID must have 17 to 20 digits")
    return token, channel_id


def set_setting(source: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^([ \t]*{re.escape(key)}[ \t]*=[ \t]*).*$")
    output, matches = pattern.subn(lambda match: match[1] + json.dumps(value), source)
    if matches != 1:
        raise ValueError(f"expected exactly one {key} assignment, found {matches}")
    return output


def main() -> None:
    if len(sys.argv) != 1:
        raise ValueError("unexpected command-line arguments")
    credentials_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not credentials_dir:
        raise ValueError("systemd credentials are unavailable")
    token, channel_id = load_values(Path(credentials_dir) / CREDENTIAL)
    original = CONFIG.read_text(encoding="utf-8")
    parsed = tomllib.loads(original)
    if "botToken" not in parsed.get("botConfig", {}):
        raise ValueError("SDLink botConfig.botToken is missing")
    if "chatChannelID" not in parsed.get("channelsAndWebhooks", {}).get("channels", {}):
        raise ValueError("SDLink channelsAndWebhooks.channels.chatChannelID is missing")

    updated = set_setting(original, "botToken", token)
    updated = set_setting(updated, "chatChannelID", channel_id)
    result = tomllib.loads(updated)
    if (
        result["botConfig"]["botToken"] != token
        or result["channelsAndWebhooks"]["channels"]["chatChannelID"] != channel_id
    ):
        raise ValueError("SDLink configuration verification failed")

    # Atomic replacement: do not truncate the previous config on failure.
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix=".sdlink-", dir=CONFIG.parent)
        temporary = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(updated)
        os.chmod(temporary, 0o600)
        os.replace(temporary, CONFIG)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        # Report the failure class, not exception text that may contain input data.
        print(
            f"SDLink runtime configuration failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        sys.exit(1)
