{
  lib,
  runCommand,
  writeText,
  sources,
  side,
}: let
  inherit (sources) pack index files src;
  # Patched sources provide a separately generated pack file and its known hash.
  # Do not make the dedicated server realise the client-only Voxy JAR.
  packFile = sources.packFile or "${src}/pack.toml";
  packFileHash = sources.packFileHash or (builtins.hashFile "sha256" packFile);

  isMetafile = entry: entry.metafile or false;
  isOptional = entry: entry.mod.option.optional or false;
  onSide = entry: builtins.elem entry.side ["" "both" side];
  clientOnly = pack.options.client-only-overrides or [];

  installed = builtins.filter (entry:
    onSide entry && !(side == "server" && builtins.elem entry.destination clientOnly))
  files;

  hash = type: value: {inherit type value;};

  # Preserve the installer's update state as well as its installed files.
  state = writeText "packwiz.json" (builtins.toJSON {
      cachedSide = side;
      packFileHash = hash "sha256" packFileHash;
      indexFileHash = hash pack.index.hash-format pack.index.hash;
      cachedFiles = builtins.listToAttrs (map (entry: {
          name = entry.file;
          value =
            {
              # Headless Packwiz accepts optional mods on the selected side.
              optionValue = onSide entry || !(isOptional entry) || (entry.mod.option.default or false);
            }
            // lib.optionalAttrs (isOptional entry) {isOptional = true;}
            // (
              if onSide entry
              then
                {
                  cachedLocation = entry.destination;
                  hash = hash (entry.hash-format or index.hash-format) entry.hash;
                }
                // lib.optionalAttrs (isMetafile entry) {
                  linkedFileHash = hash entry.mod.download.hash-format entry.mod.download.hash;
                }
              else {onlyOtherSide = true;}
            );
        })
        files);
    }
    + "\n");
in
  assert builtins.elem side ["client" "server"];
    runCommand "${pack.name}-${pack.version}-${side}" {
      passthru.configPaths =
        map (entry: entry.destination)
        (builtins.filter (entry: lib.hasPrefix "config/" entry.destination) installed);
    } ''
      mkdir -p "$out"
      install -m644 ${packFile} "$out/pack.toml"
      install -m644 ${state} "$out/packwiz.json"

      ${lib.concatMapStringsSep "\n" (entry: ''
          install -Dm644 ${lib.escapeShellArg (toString entry.source)} "$out"/${lib.escapeShellArg entry.destination}
        '')
        installed}
    ''
