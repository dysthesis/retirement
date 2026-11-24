# Transform the validated Packwiz source graph before any pack assembly.
# No import-from-derivation: every new index hash is known at evaluation time.
{
  lib,
  runCommand,
  writeText,
  sources,
  root,
  replacements,
}: let
  inherit (sources) pack index;
  oldVoxy = "mods/voxy-1.1.0+retirement.3+neoforge.jar";
  newVoxy = "mods/voxy-1.1.0+retirement.4+neoforge.jar";
  oldCreate = "mods/create.pw.toml";
  newCreate = "mods/create-1.21.1-6.0.10-retirement-panel.jar";
  specs = {
    voxy = {
      old = oldVoxy;
      new = newVoxy;
      valid = entry:
        !(entry.metafile or false)
        && entry.hash == "0f2781db79bec5c5aee3e74a2f685416fb26d306f2f30ba4d9be5980498f19fd"
        && builtins.elem oldVoxy pack.options.client-only-overrides;
    };
    create = {
      old = oldCreate;
      new = newCreate;
      valid = entry:
        (entry.metafile or false)
        && entry.destination == "mods/create-1.21.1-6.0.10.jar"
        && entry.side == "both"
        && !(entry.mod.option.optional or false)
        && entry.mod.download.hash-format == "sha512"
        && entry.mod.download.hash == "11cc8fc049d2f67f6548c7abfada6b82a3adb5c7ca410a742de04bbca76e03862c518721b88d806f6e6d768a4d68531fdb903a85859b25d1484d550cc7bafd4b";
    };
  };
  enabled = lib.mapAttrsToList (kind: replacement:
    specs.${kind} // replacement // {inherit kind;}) replacements;
  byOld = builtins.listToAttrs (map (replacement: {
    name = replacement.old;
    value = replacement;
  }) enabled);
  replaceEntry = entry: let
    replacement = byOld.${entry.file};
  in {
    file = replacement.new;
    hash = replacement.sha256;
    hash-format = "sha256";
  };
  replaceIndex = entry:
    if builtins.hasAttr entry.file byOld then replaceEntry entry else entry;
  replaceFile = entry:
    if builtins.hasAttr entry.file byOld
    then replaceEntry entry // {
      source = byOld.${entry.file}.source;
      destination = byOld.${entry.file}.new;
      side = "both";
    }
    else entry;
  files = map replaceFile sources.files;
  newIndex = index // {files = map replaceIndex index.files;};
  # Packwiz index entries have scalar TOML keys. JSON strings/booleans/integers
  # are valid TOML for these values. Verify the result by parsing it again.
  scalar = value:
    if builtins.isString value || builtins.isBool value || builtins.isInt value
    then builtins.toJSON value
    else throw "Unexpected non-scalar Packwiz index value";
  assignments = attrs: lib.concatStringsSep "\n" (lib.mapAttrsToList (key: value:
    "${key} = ${scalar value}") attrs);
  indexText = assignments (builtins.removeAttrs newIndex ["files"]) + "\n\n"
    + lib.concatMapStringsSep "\n\n" (entry: "[[files]]\n" + assignments entry) newIndex.files + "\n";
  indexHash = builtins.hashString "sha256" indexText;
  oldOverrides = pack.options.client-only-overrides or [];
  newOverrides = map (path: if path == oldVoxy && replacements ? voxy then newVoxy else path) oldOverrides;
  newPack = pack // {
    index = pack.index // {hash = indexHash;};
    options = pack.options // {client-only-overrides = newOverrides;};
  };
  # Change only the existing index hash and the Voxy client-only path. Retain
  # all other Packwiz metadata and comments, and validate semantic equality.
  packText = builtins.replaceStrings
    ([pack.index.hash] ++ lib.optional (replacements ? voxy) oldVoxy)
    ([indexHash] ++ lib.optional (replacements ? voxy) newVoxy)
    (builtins.readFile (root + "/pack.toml"));
  packFile = writeText "retirement-pack.toml" packText;
  indexFile = writeText "retirement-index.toml" indexText;
  src = runCommand "retirement-patched-packwiz-source" {} ''
    mkdir -p "$out"
    cp -r ${sources.src}/. "$out/"
    chmod -R u+w "$out"
    ${lib.concatMapStringsSep "\n" (replacement: ''
      rm -- "$out"/${lib.escapeShellArg replacement.old}
      install -Dm644 ${lib.escapeShellArg (toString replacement.source)} "$out"/${lib.escapeShellArg replacement.new}
    '') enabled}
    install -m644 ${packFile} "$out/pack.toml"
    install -m644 ${indexFile} "$out"/${lib.escapeShellArg pack.index.file}
  '';
  destinations = map (entry: entry.destination) files;
  paths = map (entry: entry.file) files;
in
  if enabled == [] then sources
  else
    assert pack.versions.minecraft == "1.21.1" && pack.versions.neoforge == "21.1.265";
    assert pack.index.hash-format == "sha256" && index.hash-format == "sha256";
    assert lib.all (replacement:
      builtins.match "[0-9a-f]{64}" replacement.sha256 != null
      && lib.length (builtins.filter (entry: entry.file == replacement.old && replacement.valid entry) sources.files) == 1
      && !(builtins.elem replacement.new (map (entry: entry.destination) sources.files))) enabled;
    assert lib.length destinations == lib.length (lib.unique destinations);
    assert lib.length paths == lib.length (lib.unique paths);
    assert builtins.fromTOML indexText == newIndex;
    assert builtins.fromTOML packText == newPack;
    sources // {
      pack = newPack;
      index = newIndex;
      inherit files src packFile;
      packFileHash = builtins.hashString "sha256" packText;
    }
