# NeoForge migration

Retirement 2.0.0 keeps Minecraft **1.21.1** and pins **NeoForge 21.1.265** in `packwiz/pack.toml`. The Nix server reads that same pin. Clients support **Java 21**, which disables only C2ME's optional native-math module. The dedicated Nix server uses **Java 25** to enable that module; private builds still use JDK 21.

Use a fresh launcher instance and a new world. Back up existing saves before experimenting: Fabric-to-NeoForge world, backpack and accessory data conversion is not established. No existing saves or live installations are modified by this repository migration.

## Removed standalone components

These are retired loader-specific artifacts, not silently dropped gameplay mods:

| Removed | Replacement / reason |
| --- | --- |
| Fabric Loader 0.20.1 | NeoForge 21.1.265. |
| Fabric API | Forgified Fabric API for the remaining supported Fabric integrations. |
| Fabric Language Kotlin | Native Kotlin callers use Kotlin for Forge; no retained Fabric caller requires FLK. |
| Trinkets | Native accessory callers use Curios and Caelus. Existing equipped data is not automatically converted. |
| Mod Menu | NeoForge's built-in Mods screen and native configuration screens. |
| Text Placeholder API | No remaining caller. |
| ZConfig | Native Fast Noise supplies its own configuration. |
| `scripts/build-cultural-delights.py` | Upstream native Cultural Delights 0.19.8 has the correct two-argument fuel hook; the Refabricated bytecode rewrite is obsolete. |

## Split-project replacements

Direct native builds keep the existing project where available. The following move to a native upstream project or maintained port instead:

| Previous component | NeoForge replacement |
| --- | --- |
| C2ME Fabric | C2ME NeoForge |
| CIT Resewn | CIT Resewn (NeoForge) |
| Connectible Chains | Reconnectible Chains |
| Continuity | Continuity: NeoForged; not the Connector-only release on the original project |
| Crosshair Addons and WalksyLib | Reproducible native upstream targets, with 1.21.1 HUD overloads corrected |
| Dark Loading Screen | Dark Loading Screen (NeoForge) |
| Farmer's Delight Refabricated | Farmer's Delight 1.3.4 |
| Friends&Foes Fabric/Quilt | Friends&Foes NeoForge 5.0.4 |
| ImmersiveThunder Fabric | Official NeoForge 1.3.0 release on CurseForge |
| Jade Addons Fabric | Jade Addons NeoForge |
| Krypton | Krypton Reno |
| Litematica | Forgematica |
| MaLiLib | MaFgLib |
| My Nether's Delight Refabricated | My Nether's Delight |
| Particular | Particular Reforged |
| Stfu | Stfu Reforged |
| Sophisticated Backpacks Fabric port | Official Sophisticated Backpacks |
| Sophisticated Core Fabric port | Official Sophisticated Core |
| Status Effect Bars | Status Effect Bars Reforged, with its required Stylish Effects dependency |
| The Bumblezone Fabric | Official Bumblezone NeoForge, same 7.17.3 version |
| Very Many Players Fabric | Very Many Players NeoForge; unofficial alpha port |
| Wakes | Wakes Reforged |
| Weather Glass Fabric | Official NeoForge 0.6.2 release |

Exact versions, download hashes and loader-specific dependency metadata are in `packwiz/mods/*.pw.toml`. Forgematica's upstream release marks its sources jar as primary: keep the explicitly selected executable jar when updating it.

## Replaced private binaries

All six previous private jars are removed from the shipped pack:

- `culturaldelights-1.21.1-0.19.8-refabricated+retirement.1.jar` → upstream native Cultural Delights 0.19.8.
- `emi-1.1.24+retirement.1+1.21.1+fabric.jar` → native NeoForge build; empty repair-material tags retain same-item repairs and never become Barrier ingredients.
- `emi_loot-0.7.10+1.21+retirement.1+fabric.jar` → native NeoForge build, retaining immutable asynchronous recipe snapshots.
- `emi-letsdo-compat-2.0.3+retirement.2.jar` → `retirement.3+neoforge`, retaining exact consumed containers and in-world fondue/grape guidance.
- `emi-rechiseled-1.0.0+retirement.2.jar` → `retirement.3+neoforge`, retaining synchronized recipes and native conversion ratios.
- `voxy-0.2.15-beta+retirement.2.jar` → pinned native Voxy fork, retaining finite-fluid classification and native fluid tinting.

The `scripts/build-*.sh` recipes pin sources, dependencies and observed output checksums. Their semantic checks exercise real native recipes/material planning, native chiseling conversions, and fluid versus waterlogged-block classification. EMI Loot's Fabric-mapped compile-only input serves upstream shared sources; it is not shipped. Private Voxy builds remain subject to upstream's redistribution restriction; do not publish the export.

Crosshair Addons and WalksyLib now use native private builds instead of their former Fabric downloads; `scripts/build-crosshair.sh OUTPUT_DIRECTORY` rebuilds both. Axiom remains on its original supported-version artifact through Connector; every other shipped mod uses a native or multi-loader artifact.

Small Ships 2.0.2 uses a private lifecycle repair rebuilt by `scripts/build-smallships.sh OUTPUT_DIRECTORY`. Its repaired jar is recorded in the source snapshot consumed by Nix. Only its native config handler and private version metadata differ from the released jar: unloaded and remote/default in-memory configs are not parsed as files; ordinary file loading, reloading and migration stay intact.

Spelunkery, Easy Anvils and Easy Magic are retired. Recipes requiring Spelunkery-only inputs are removed. Create 6.0.10 now supplies its own vanilla-ore crushing, mineral recycling and washing recipes with valid native outputs, unchanged native probabilities and durations. The optional Oreganized glance recipes retain their 80% crushed-lead output and 250-tick duration without the removed raw-lead nugget.

Create's splashing catalyst tag includes `#minecraft:water`, so fans wash through both ordinary water and Streams Reflowing source/flowing water. The patch extends the native tag instead of replacing it.

The compatibility datapack migrates Deeper and Darker's cutting, crushing and sawing integrations to the native Farmer's Delight 1.3, Create 6 and Mekanism 10 codecs, preserving recipe IDs, quantities, chances and durations. My Nether's Delight bastion loot modifiers use Farmer's Delight's native `table` field.

Supplementaries' native flax straw modifier uses the 1.21 item predicate. Only a straw-harvesting tool yields one extra straw from a mature lower half; the obsolete mirrored loot table is removed so the native modifier cannot duplicate that drop.

`client-only-overrides` in `packwiz/pack.toml` is shared by the Nix server filter and the patched exporter. It keeps Voxy, EMI Rechiseled, Crosshair Addons and WalksyLib in the client only. Build servers through Nix; a raw Packwiz installer does not apply this private-jar list.

The Nix server copies mods into a real directory, like its configuration. NeoForge's early bootstrap discovery does not descend through a directory symlink; a symlinked `mods` directory silently loses Connector and other bootstrap services.

VMP's optional nearby-entity tracking optimization is disabled because it overwrites the chunk-manager call Sable needs to tick sub-level entities. C2ME and VMP's remaining optimizations stay enabled; Sable and Create Aeronautics are retained.

Thermoo Patches 0.1.1 connects Frostiful and Scorchful to Serene Seasons, including tropical seasons, and supplies their native Friends&Foes integration. Serene Seasons alone changes seasonal precipitation but does not populate Thermoo's season event.

Clients retain EMI and include the full JEI 19.32.0.359 runtime for EMI's bundled JEI bridge. Create, its JEI-only addons and Cataclysm then expose their processing and progression recipes without replacing the EMI frontend. JEI is not installed on dedicated servers. Attach the client integration probe only after EMI finishes loading; it rejects an unfinished asynchronous reload explicitly.

The patched exporter sorts both loose overrides and embedded non-CDN downloads, so identical private packs produce identical bytes.

## Mod installation sides

Packwiz's `side` field controls downloaded mods; `client-only-overrides` controls private raw jars. These classifications apply to both Nix outputs and the private Modrinth export, not just where a mod's code executes.

- **Client only:** rendering, audio, HUD and client tools. Fusion, Sound Physics Remastered, CreativeCore and MidnightLib are excluded from the server; the latter two have no server consumers in this pack.
- **Server only:** VMP, Create Liquid Fuel, Forgiving Void, Naturally Trimmed, NetherPortalFix, Seasonal Let's Do, ServerCore, Skeleton AI Fix, Structure Layout Optimizer, Incendium, Nullscape, Structory, Tidal Towns, YUNG's Better Dungeons and YUNG's Better Mineshafts.
- **Both:** content mods, their shared dependencies, and useful two-sided integrations. Keep Jade and its addons, Xaero's maps, Axiom, Elytra Trims, EMI, EMI Loot, EMI Ores and EMI Let's Do compatibility on the server as well as the client. Their server logic is not replaced by the client UI. Async Logger, Krypton Reno and Fast Noise support both installations. Stellarity and Terralith retain their client resources; Tectonic and other optional-client worldgen integrations remain available for local worlds.

Project-wide environment labels are not sufficient dependency evidence: Quark requires Biolith on both sides; several gameplay mods require Cloth Config; Fish of Thieves and Thermoo Patches require YACL. Config Manager also installs client defaults, and CrashExploitFixer protects shared packet/text handling, so both remain on both sides.

Wakes Reforged's pinned release advertises both sides, but its wake and Sable mixins are all client-only and it has no packet handlers; it stays client-only. Likewise, EMI Let's Do compatibility stays on both sides because its private build still supplies server cake-cutting recipes, despite its client-side EMI dependency.

The client output is not a feature-identical singleplayer distribution: server-only mods are deliberately absent, including the two YUNG structure generators and the server gameplay fixes. Use the dedicated server output for the complete multiplayer world behavior.

## Build and verification entrypoints

```sh
nix build .#modpack-client .#modpack-server .#modrinth
nix flake check -L
```

Each downloaded artifact is a separately hash-verified Nix fetch, shared by client, server and Modrinth builds. Export digests are cached per artifact too. Only indexed Packwiz inputs affect assembly; package assembly and export run without network access and track their source and tool dependencies normally. Shared logic lives in `nix/lib`; `nix/packages` declares the outputs.

`just rehash` refreshes the Packwiz index and pack hash chain. After deliberately changing a download URL or CurseForge file ID, use `just rehash mods/appleskin.pw.toml` (or several Packwiz-relative metafile paths) to re-pin those download hashes first. The recipe uses structured Nix prefetch results, preserves the rest of each metafile, and warms the same per-file Nix cache used by builds. Re-pinning intentionally trusts the newly downloaded bytes; review the metadata changes.

`checks.modpacks` verifies both installed trees, side filtering, private client-only overrides, installer update state and hash-update parsing. The exporter independently checks its payload inventory, checksums, sides and embedded files before accepting an archive; Packwiz handles the export format and URL encoding.

The NixOS check boots the actual server twice, exercises protocol/firewall access, high-altitude terrain, saved blocks, ordinary/Fortune/Silk Touch ore drops, food/flax/wildlife integration and biome generation. `scripts/CheckClientRepairs.java` attaches to a joined NeoForge client for live EMI repair verification.

`scripts/CheckPackIntegrations.java` attaches to a running disposable NeoForge server or joined client. It checks Thermoo's season against Serene Seasons, exercises native Create crushing with stone/deepslate diamond ores and mineral stones, verifies their output validity, leading-result probabilities and durations, and checks Create's washing predicate for ordinary water, both Streams fluids and non-water. The client also checks Create and Cataclysm recipes through EMI's actual item lookups. Repeat it after `/season set mid_winter` and `/season set mid_summer`.

`vendor/adrenaline` is an unused upstream historical Fabric reference, not an input to either pack or server; its archive is left intact.
