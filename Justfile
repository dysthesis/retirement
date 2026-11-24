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

# Export the effective Nix pack, including any enabled private builds.
export:
	nix build .#modrinth --no-link --print-out-paths

# Refresh pack/index hashes; pass Packwiz-relative metafiles to re-pin downloads too.
[positional-arguments]
rehash *metafiles:
	python3 scripts/rehash.py "$@"

cmd +command:
    @printf '%s\n' {{quote(command)}} | ssh archon@10.0.60.2 'test -p /run/minecraft/retirement-home.stdin && cat > /run/minecraft/retirement-home.stdin'
