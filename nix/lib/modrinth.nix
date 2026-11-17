{
  runCommand,
  writeText,
  python3,
  packwiz,
  sources,
}: let
  downloads = writeText "packwiz-downloads.json" (builtins.toJSON (map (entry: {
    inherit (entry) file url;
    source = toString entry.source;
    hashes = toString entry.hashes;
  }) (builtins.filter (entry: entry.metafile or false) sources.files)));
in
  runCommand "${sources.pack.name}-${sources.pack.version}.mrpack" {
    nativeBuildInputs = [packwiz python3];
  } ''
    export HOME="$TMPDIR"

    cp -r ${sources.src} packwiz
    chmod -R u+w packwiz

    cd packwiz
    python3 ${./modrinth.py} ${downloads} "$TMPDIR/packwiz-cache" "$out"
  ''
