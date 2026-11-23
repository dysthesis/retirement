# Dynamic Surroundings weather rendering

Version 0.4.9 adds `weatherOptions.enableGroundFog` as a separate switch. `weatherOptions.enableDynamicClouds` was added in 0.4.8. Both default to true and both are suppressed while a shader pack is active. Disable both to remove Dynamic Surroundings' ground mist and replacement cloud renderer, leaving normal fog and clouds to the existing rendering stack. Do not change Particle Rain, the game's cloud on/off setting or other weather controls.

Source: https://dynamic-surroundings.readthedocs.io/en/latest/config/modconfiguration.html#weatheroptions

## Prerequisite and test

For shader-free clients with Voxy, first verify the effective `config/voxy-config.json` contains `adapt_cloud_distance: false` and `cloud_distance: 0` (the earlier Voxy workload patch). Otherwise returning to Sodium clouds may activate Voxy's extended cloud radius, and increase rather than reduce cost. The result also depends on the client's normal cloud setting. This patch is independent of the scan-radius patch; apply either or both.

Back up the live `config/dsurround/dsurround.json` before updating an existing instance. Merge the two settings into the existing `weatherOptions` object if custom settings are present. Restart and check effective values. Compare cloud-only and ground-fog-only changes with shaders disabled, with the same camera, weather and terrain cache. Check cloud appearance, ground mist and p95/p99 frame times in clear weather, rain and swamps. Run a shader-enabled control. Restore the previous values if the new renderer is slower or visual quality is unacceptable. Ordinary fog settings remain unchanged.

Run `just rehash` from the repository root after applying this patch.
