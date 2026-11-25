# Prism Launcher instance that joins one deployment and updates from its Packwiz host.
{
  lib,
  fetchurl,
  python3,
  runCommand,
  writeText,
  zip,
  domain,
  port ? 25565,
}: let
  pack = builtins.fromTOML (builtins.readFile ../../packwiz/pack.toml);
  address = domain + lib.optionalString (port != 25565) ":${toString port}";

  clientMinMemMiB = 4096;
  clientMaxMemMiB = 12288;

  clientJvmArgs = lib.concatStringsSep " " [
    "-XX:+UseZGC"
    "-XX:+ZGenerational"
    "-XX:ReservedCodeCacheSize=512m"
    "-Xlog:gc*,safepoint,codecache:file=gc.log:time,uptime,level,tags:filecount=10,filesize=50m"
  ];

  components = writeText "retirement-home-mmc-pack.json" (builtins.toJSON {
    formatVersion = 1;
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
  });
  installer = fetchurl {
    url = "https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar";
    hash = "sha256-qPuyTcYEJ46X9GiOgtPZGjGLmO/AjV2/y8vKtkQ9EWw=";
  };
in
  runCommand "retirement-home-bootstrap" {
    nativeBuildInputs = [python3 zip];
    serverAddress = address;
    passthru = {inherit clientJvmArgs domain;};
  } ''
    mkdir -p work/minecraft "$out"
    cp ${installer} work/minecraft/packwiz-installer-bootstrap.jar
    cp ${components} work/mmc-pack.json

    # Prism Launcher reads these as instance-specific JVM and memory settings.
    cat > work/instance.cfg <<'EOF'
    [General]
    ConfigVersion=1.3
    ExportAuthor=dysthesis
    ExportName=Retirement Home
    ExportSummary=Retirement NeoForge modpack
    ExportVersion=${pack.version}
    InstanceType=OneSix
    ManagedPack=false
    MaxMemAlloc=${toString clientMaxMemMiB}
    MinMemAlloc=${toString clientMinMemMiB}
    OverrideCommands=true
    OverrideJavaArgs=true
    OverrideMemory=true
    JvmArgs="${clientJvmArgs}"
    PreLaunchCommand=\"$INST_JAVA\" -jar packwiz-installer-bootstrap.jar -g -s client https://${domain}/modpack/pack.toml
    name=Retirement Home

    [UI]
    EOF

    # Minecraft servers.dat is a big-endian, named binary tag (NBT) compound.
    python3 - <<'PYTHON'
    import os
    import struct
    from pathlib import Path

    def utf(value):
        encoded = value.encode("utf-8")
        assert len(encoded) <= 65535
        return struct.pack(">H", len(encoded)) + encoded

    data = b"\x0a" + utf("")  # Root TAG_Compound
    data += b"\x09" + utf("servers")  # TAG_List
    data += b"\x0a" + struct.pack(">i", 1)  # One TAG_Compound
    data += b"\x08" + utf("name") + utf("Retirement Home")
    data += b"\x08" + utf("ip") + utf(os.environ["serverAddress"])
    data += b"\x00\x00"  # End server and root compounds
    Path("work/minecraft/servers.dat").write_bytes(data)
    PYTHON

    cat > work/README.txt <<'EOF'
    Retirement Home - Minecraft ${pack.versions.minecraft}, NeoForge ${pack.versions.neoforge}

    Import RetirementHome-bootstrap.zip using Prism Launcher -> Add Instance -> Import.
    Configure Java 25 under Edit Instance -> Settings -> Java before launch.

    JVM preset for the profiled 32 GiB-RAM clients:
      Collector: Generational ZGC (Java 25, -XX:+UseZGC)
      Initial/minimum Java heap: 4096 MiB
      Maximum Java heap: 12288 MiB
      JVM GC and safepoint log: gc.log in the Java process's working directory
      Logs rotate: up to 10 x 50 MiB files

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
    https://${domain}/modpack/pack.toml
    EOF

    (cd work && zip -qr "$out/RetirementHome-bootstrap.zip" \
      instance.cfg mmc-pack.json README.txt \
      minecraft/packwiz-installer-bootstrap.jar minecraft/servers.dat)
  ''
