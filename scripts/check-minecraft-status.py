"""Check a Minecraft status response, without bypassing online-mode authentication."""

import sys

from mcstatus import JavaServer

address, version, max_players = sys.argv[1:]
status = JavaServer.lookup(address, timeout=5).status()
assert status.version.name == version, status.version
assert status.players.max == int(max_players), status.players
