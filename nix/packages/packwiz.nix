{packwiz}:
# Sort exported files and keep private client libraries off dedicated servers.
packwiz.overrideAttrs (old: {
  patches = (old.patches or []) ++ [../lib/packwiz-deterministic-overrides.patch];
})
