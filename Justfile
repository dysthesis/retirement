# General entrypoint for the `packwiz` CLI without having to worry about cd-ing into the correct directory.
[working-directory: 'packwiz']
pack *args:
	packwiz {{args}}

# List the installed mods in the modpack
ls: (pack "list")

# Install a mod to the modpack, defaulting to Modrinth as the source, which can be changed using `--from`.
[arg("from", long="from")]
install from="modrinth" *args: (pack from "install" args)

# Remove a mod
rm mod: (pack "remove" mod)

# Export private mrpack; the unofficial Voxy backport must not be redistributed.
export: (pack "modrinth export")

# Rebuild the pinned Voxy backport and private mrpack without updating existing mods.
build-voxy:
	scripts/build-voxy.sh
