# Minecraft clients require Java 25; the dev shell keeps JDK 21 for reproducible Voxy builds.
# Fresh profiles get Wands shortcuts from packwiz/options.txt; existing players keep their Controls.
# Keep preserve = true on its index entry so updates never overwrite player options.
# Resource layers put Animations before Extensions and Icon Xaero's before Icon Fresh.
# Photon stays opt-in through Iris (O); shader hardware requirements are not pack defaults.
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

# Export a deterministic private mrpack using the devShell's patched Packwiz (also used by .#modrinth).
# The unofficial Voxy backport must not be redistributed.
export: (pack "modrinth export")

# Rebuild and verify the pinned private Voxy backport; refresh pack metadata separately.
build-voxy:
	scripts/build-voxy.sh

# Rebuild the pinned EMI empty-repair-tag fix; refresh pack metadata separately.
build-emi:
	scripts/build-emi.sh

# Rebuild unique food recipe views without duplicating the mods' native EMI plugins.
build-emi-compat:
	scripts/build-emi-compat.sh packwiz/mods

# Rebuild EMI's chisel conversions from Rechiseled's synchronized recipe registry.
build-emi-rechiseled:
	scripts/build-emi-compat.sh packwiz/mods rechiseled
