# Dynamic Surroundings block-effect scan radius

The pack pins Dynamic Surroundings 0.4.9 for NeoForge 1.21.1. Its documented `blockEffects.blockEffectRange` accepts 16–64 blocks and defaults to 40. Since 0.4.8, its search region is spherical. Set it to 24 to reduce environmental scan coverage while retaining nearby block effects. The nominal spherical volume is 21.6% of the 40-block volume; this is not a measurement of block accesses or client tick time. Existing ripple, waterfall, firefly, acoustic and fog settings are unchanged.

Source: https://dynamic-surroundings.readthedocs.io/en/latest/config/modconfiguration.html#blockeffects

## Test and roll back

This modifies the pack's existing direct configuration, not a Config Manager default. Back up `config/dsurround/dsurround.json` in existing client instances before updating the pack. A launcher may replace the whole distributed file, so merge the one changed field into any customised configuration if needed. Restart Minecraft. Check the effective value in the mod's config screen. Do not replace the complete generated config with a partial snippet.

Use `/dsconflicts` to see automatic compatibility switches and `/dsprofile` to record the mod's JFR profile. Compare the same route through a complex settlement, with identical weather, shader state and visible effects. Compare client tick work and p95/p99 frame times. Also check steam, flames and other nearby effects. If effect coverage is too limited, test 32; restore 40 or the original value to roll back. No server simulation settings are changed.

Run `just rehash` from the repository root after applying this patch.
