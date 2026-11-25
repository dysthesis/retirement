# Zip a Prism Launcher instance import from Nix values.
{
  lib,
  python3,
  runCommand,
  writeText,
  zip,
}: {
  # Name of the ZIP in $out.
  fileName,
  # instance.cfg sections, for example {General.name = "Pack";}.
  settings,
  # mmc-pack.json component list.
  components,
  # Multiplayer list entries: [{name = "Server"; ip = "host:port";}].
  servers ? [],
  # Extra archive members: {"minecraft/file" = path;}.
  files ? {},
}: let
  # Prism parses instance.cfg with QSettings, which splits unquoted values at commas.
  quote = value: ''"${lib.escape ["\\" "\""] (lib.generators.mkValueStringDefault {} value)}"'';
  instance = writeText "instance.cfg" (lib.generators.toINI {
      mkKeyValue = key: value: "${key}=${quote value}";
    }
    settings);
  pack = writeText "mmc-pack.json" (builtins.toJSON {
    formatVersion = 1;
    inherit components;
  });
  members =
    {
      "instance.cfg" = instance;
      "mmc-pack.json" = pack;
    }
    // files;
in
  runCommand (lib.removeSuffix ".zip" fileName) {
    nativeBuildInputs = [python3 zip];
    passthru = {inherit settings;};
  } ''
    mkdir -p work "$out"
    ${lib.concatStrings (lib.mapAttrsToList (member: source: ''
        install -Dm644 ${source} ${lib.escapeShellArg "work/${member}"}
      '')
      members)}
    ${lib.optionalString (servers != []) ''
      python3 ${./servers-dat.py} ${writeText "servers.json" (builtins.toJSON servers)} work/minecraft/servers.dat
    ''}
    (cd work && zip -qrXD "$out"/${lib.escapeShellArg fileName} .)
  ''
