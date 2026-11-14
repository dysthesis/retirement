"""NixOS driver test: real service, network protocol, chunk generation and save/reload.

Run through nix flake check, not directly. Packwiz changes require refreshing both
modpack hashes in nix/packages/. Fresh-world smoke only: existing-world upgrades,
authenticated player logins, backups and sustained load remain untested.
"""

import json
import shlex

with open("@settings@") as settings_file:
    settings = json.load(settings_file)

unit = "minecraft-server-retirement.service"
log_file = settings["log"]
tmux = settings["tmux"]


def command(text):
    return f"{tmux} send-keys -l -- {shlex.quote(text)} && {tmux} send-keys Enter"


def expect(command_text, marker):
    server.wait_until_succeeds(
        command(command_text) + f" && grep -F -- {shlex.quote(marker)} {shlex.quote(log_file)}",
        timeout=600,
    )


start_all()
client.wait_for_unit("multi-user.target")
try:
    for boot in range(2):
        server.wait_for_unit(unit)
        # A separate machine exercises the firewall and the Minecraft protocol.
        client.wait_until_succeeds(settings["status"], timeout=600)
        server.succeed(command("forceload add 0 0"))
        marker = f"retirement-check-loaded-{boot}"
        expect(f"execute if loaded 0 100 0 run say {marker}", marker)
        if boot == 0:
            server.succeed(command("setblock 0 100 0 minecraft:diamond_block"))
        # Unique per boot: only a live server reading the saved chunk can pass.
        marker = f"retirement-check-persisted-{boot}"
        expect(f"execute if block 0 100 0 minecraft:diamond_block run say {marker}", marker)
        assert server.succeed(f"systemctl show {unit} -p NRestarts --value").strip() == "0"
        server.succeed(f"systemctl stop {unit}", timeout=120)
        assert server.succeed(f"systemctl show {unit} -p Result --value").strip() == "success"
        assert server.succeed(f"systemctl show {unit} -p ExecMainStatus --value").strip() == "0"
        if boot == 0:
            server.succeed(f"systemctl start {unit}")
finally:
    print(server.execute(f"journalctl -u {unit} --no-pager")[1])
    print(server.execute(f"cat {shlex.quote(log_file)}")[1])
