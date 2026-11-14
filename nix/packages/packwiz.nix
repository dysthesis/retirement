{packwiz}:
# shortcut: only loose files are embedded, sort bundled downloads if non-CDN sources are added.
packwiz.overrideAttrs (old: {
  patches = (old.patches or []) ++ [./packwiz-deterministic-overrides.patch];
})
