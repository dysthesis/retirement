"""NixOS driver test: real service, terrain, mod integration and save/reload.

Run through nix flake check, not directly. Packwiz changes require refreshing the
modpack and export hashes in nix/packages/. Fresh-world smoke only: existing-world
upgrades, authenticated player logins, backups and sustained load remain untested.
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
        expect(f"execute if loaded 0 500 0 run say {marker}", marker)
        if boot == 0:
            server.succeed(command("setblock 0 500 0 minecraft:diamond_block"))
        # Above vanilla's height limit: also catches Tectonic falling back to defaults.
        marker = f"retirement-check-persisted-{boot}"
        expect(f"execute if block 0 500 0 minecraft:diamond_block run say {marker}", marker)
        server.succeed(command("setblock 1 500 0 minecraft:chest"))
        for item, accepted in [
            ("moredelight:toast", True),
            ("minecraft:cookie", True),
            ("minecraft:stone", False),
        ]:
            server.succeed(command(f"item replace block 1 500 0 container.0 with {item}"))
            marker = f"retirement-check-jar-{item.split(':')[1]}-{boot}"
            condition = "if" if accepted else "unless"
            expect(
                f"execute {condition} items block 1 500 0 container.0 "
                f"#supplementaries:jar_cookies run say {marker}",
                marker,
            )
        server.succeed(command("setblock 3 499 0 minecraft:farmland"))
        for age, half, tool_item, harvests in [
            (7, "lower", "farmersdelight:iron_knife", True),
            (6, "lower", "farmersdelight:iron_knife", False),
            (7, "lower", "minecraft:stick", False),
            (7, "upper", "farmersdelight:iron_knife", False),
        ]:
            server.succeed(command("setblock 3 501 0 minecraft:air"))
            server.succeed(command("setblock 3 500 0 minecraft:air"))
            server.succeed(command("data merge block 1 500 0 {Items:[]}"))
            server.succeed(command(f"setblock 3 500 0 supplementaries:flax[age={age},half=lower]"))
            if age == 7:
                server.succeed(command("setblock 3 501 0 supplementaries:flax[age=7,half=upper]"))
            y = 501 if half == "upper" else 500
            key = f"{age}-{half}-{tool_item.split(':')[1]}-{boot}"
            marker = f"retirement-check-flax-state-{key}"
            expect(
                f"execute if block 3 {y} 0 supplementaries:flax[age={age},half={half}] "
                f"run say {marker}",
                marker,
            )
            server.succeed(command(f"loot insert 1 500 0 mine 3 {y} 0 {tool_item}"))
            marker = f"retirement-check-flax-drop-{key}"
            condition = "if" if harvests else "unless"
            expect(
                f"execute {condition} items block 1 500 0 container.* "
                f"farmersdelight:straw run say {marker}",
                marker,
            )
        server.succeed(command("setblock 3 501 0 minecraft:air"))
        server.succeed(command("setblock 3 500 0 minecraft:air"))
        server.succeed(command("setblock 1 500 0 minecraft:air"))
        for biome, accepted in [
            ("terralith:lavender_forest", True),
            ("terralith:siberian_taiga", True),
            ("minecraft:plains", True),
            ("minecraft:desert", False),
        ]:
            # Biome lookup samples neighboring cells, not just the filled cell.
            server.succeed(command(f"fillbiome 4 496 4 12 504 12 {biome}"))
            marker = f"retirement-check-squirrel-{biome.split(':')[1]}-{boot}"
            condition = "if" if accepted else "unless"
            expect(
                f"execute {condition} biome 8 500 8 "
                f"#wildernature:spawns_squirrel run say {marker}",
                marker,
            )
        for dimension, biome in [
            ("minecraft:the_end", "nullscape:crystal_peaks"),
            ("minecraft:overworld", "fishofthieves:tropical_island"),
        ]:
            key = f"{biome.split(':')[1]}_{boot}"
            server.succeed(
                command(
                    f"execute in {dimension} store success storage retirement:check "
                    f"{key} byte 1 run locate biome {biome}"
                )
            )
            marker = f"retirement-check-{key}"
            expect(
                f"execute if data storage retirement:check {{{key}:1b}} run say {marker}",
                marker,
            )
        assert server.succeed(f"systemctl show {unit} -p NRestarts --value").strip() == "0"
        server.succeed(f"systemctl stop {unit}", timeout=120)
        assert server.succeed(f"systemctl show {unit} -p Result --value").strip() == "success"
        assert server.succeed(f"systemctl show {unit} -p ExecMainStatus --value").strip() == "0"
        if boot == 0:
            server.succeed(f"systemctl start {unit}")
finally:
    print(server.execute(f"journalctl -u {unit} --no-pager")[1])
    print(server.execute(f"cat {shlex.quote(log_file)}")[1])
