# WATUT simple GUI representation

Retirement pins WATUT `watut-neoforge-1.21.0-1.2.7.jar`. The upstream 1.21.0 branch's `RenderHelper.useDynamicGUISystem()` returns false if either the server simple-GUI flag or the client privacy flag is true. The detailed render path exits before the secondary screen render, framebuffer readback (`glReadPixels`) and submission for compression when this condition is false. The client flag stops detailed GUI capture/sending by that client; it does not guarantee that it stops processing detailed GUI images sent by other clients. Basic activity indicators remain available, subject to existing settings. Item information settings are unchanged.

Sources:
- https://github.com/Corosauce/WATUT/blob/1.21.0/src/main/java/com/corosus/watut/client/screen/RenderHelper.java
- https://github.com/Corosauce/WATUT/blob/1.21.0/src/main/java/com/corosus/watut/config/ConfigClient.java
- https://github.com/Corosauce/WATUT/blob/1.21.0/src/main/java/com/corosus/watut/config/ConfigServerControlledSyncedToClient.java
- https://www.curseforge.com/minecraft/mc-mods/what-are-they-up-to

## Distribution and existing clients

This is a client-only Config Manager default, not a replacement for a live config. The pack already uses Config Manager 1.0.1. A fresh installation should receive `config/watut-client.toml` with `[general]` and `dontSendDetailedGUIInfo = true`; confirm the effective setting after first launch and restart. Existing clients may already have a file and will need to opt in. With Minecraft closed, back up that file and set only that key in the existing `[general]` table. Do not reset other WATUT settings. Restore the previous value to roll back.

For a uniform server-wide policy on an existing deployment, the WATUT author documents the following command (requires operator permission):

```text
/coro config common set watut-server.toml dynamicGuiUseOldSimpleGUIVisual true
```

When running from the dedicated server console, omit the leading slash. The repository's `just cmd` recipe can send a console command if its host and service path are correct. Confirm that the command succeeds and that two connected clients show the simple representation. The server flag is authoritative for the detailed capture path. If the runtime file is writable, verify that the value survives a server restart; otherwise arrange persistence using the deployment's existing configuration management. Do not create a partial immutable NeoForge server config in the Nix store. To roll back the server policy, set the flag to false (or its prior value); individual client privacy flags still apply.

## Acceptance

Compare repeated GUI openings and closings, including inventories, EMI and Xaero World Map, with the same resolution, shaders and world. Test with two connected clients. Compare per-opening frame-time spikes and the WATUT render path in a client profile. Default constant image updates are already disabled upstream, so do not assume sustained FPS will increase. Check basic GUI, typing and idle indicators. The exact pinned binary and live runtime have not been tested here.

Run `just rehash` from the repository root after applying this patch. Stage the new default and refreshed hash files before Nix evaluation.
