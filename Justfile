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

# Export a deterministic private mrpack using the devShell's patched Packwiz (also used by .#modrinth).
export: (pack "modrinth export")
