# Prism Launcher instance that joins one deployment and updates from its Packwiz host.
{
  lib,
  callPackage,
  fetchurl,
  writeText,
  domain,
  port ? 25565,
  # instance.cfg overrides, merged over the defaults below.
  settings ? {},
}: let
  pack = builtins.fromTOML (builtins.readFile ../../packwiz/pack.toml);
  address = domain + lib.optionalString (port != 25565) ":${toString port}";
  packUrl = "https://${domain}/modpack/pack.toml";
  fileName = "RetirementHome-bootstrap.zip";

  instance =
    lib.recursiveUpdate {
      General = {
        ConfigVersion = "1.3";
        ExportAuthor = "dysthesis";
        ExportName = "Retirement Home";
        ExportSummary = "Retirement NeoForge modpack";
        ExportVersion = pack.version;
        InstanceType = "OneSix";
        ManagedPack = false;
        name = "Retirement Home";
        # Profiled on 32 GiB-RAM clients.
        MinMemAlloc = 4096;
        MaxMemAlloc = 12288;
        JvmArgs = lib.concatStringsSep " " [
          "-XX:+UseZGC"
          "-XX:+ZGenerational"
          "-XX:ReservedCodeCacheSize=512m"
          "-Xlog:gc*,safepoint,codecache:file=gc.log:time,uptime,level,tags:filecount=10,filesize=50m"
        ];
        OverrideCommands = true;
        OverrideJavaArgs = true;
        OverrideMemory = true;
        PreLaunchCommand = ''"$INST_JAVA" -jar packwiz-installer-bootstrap.jar -g -s client ${packUrl}'';
      };
    }
    settings;
  general = instance.General;

  readme = writeText "README.txt" ''
    ${general.name} - Minecraft ${pack.versions.minecraft}, NeoForge ${pack.versions.neoforge}

    Import ${fileName} using Prism Launcher -> Add Instance -> Import.
    Configure Java 25 under Edit Instance -> Settings -> Java before launch.

    JVM preset:
      Initial/minimum Java heap: ${toString general.MinMemAlloc} MiB
      Maximum Java heap: ${toString general.MaxMemAlloc} MiB
      JVM arguments: ${general.JvmArgs}

    These are client heap limits, NOT a measure of total Minecraft process RAM.
    On machines with about 16 GiB physical RAM, reduce the Prism maximum heap
    to 8192 MiB or less, and monitor for paging. An 8 GiB heap may still be too
    small for some high-memory scenes; the profiles do not establish a universal
    requirement. Do not change -Xms/-Xmx by adding them to the JVM arguments.

    This bootstrap applies these defaults only when importing a new instance.
    Existing instances must be changed under Edit Instance -> Settings -> Java.
    Replacing the ZIP does not update the JVM configuration of old imports.

    Join ${address} over the private Tailnet.
    The pre-launch updater downloads the client pack from:
    ${packUrl}
  '';
in
  callPackage ../lib/prism-instance.nix {} {
    inherit fileName;
    settings = instance;
    components = [
      {
        uid = "net.minecraft";
        version = pack.versions.minecraft;
      }
      {
        uid = "net.neoforged";
        version = pack.versions.neoforge;
      }
    ];
    servers = [
      {
        name = general.name;
        ip = address;
      }
    ];
    files = {
      "README.txt" = readme;
      "minecraft/packwiz-installer-bootstrap.jar" = fetchurl {
        url = "https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar";
        hash = "sha256-qPuyTcYEJ46X9GiOgtPZGjGLmO/AjV2/y8vKtkQ9EWw=";
      };
    };
  }
