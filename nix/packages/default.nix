{inputs, ...}: {
  perSystem = {
    pkgs,
    lib,
    system,
    ...
  }: let
    packwiz = pkgs.callPackage ./packwiz.nix {};
    root = ../../packwiz;
    stockSources = pkgs.callPackage ../lib/packwiz.nix {inherit root;};
    pins = builtins.fromJSON (builtins.readFile ../patched-mods.json);
    # One build platform gives every pack the same JAR bytes and hash.
    # Other platforms can substitute these outputs or use a Linux builder.
    buildPkgs = inputs.nixpkgs.legacyPackages.x86_64-linux;
    candidates = lib.mapAttrs (kind: pin: buildPkgs.callPackage ./patched-mod.nix {
      inherit kind;
      inherit (pin) sha256;
    }) pins;
    replacements = lib.mapAttrs (kind: pin: {
      source = candidates.${kind};
      sha256 = if pin.sha256 == null
        then throw "retirement: pin ${kind} before enabling its custom build in nix/patched-mods.json"
        else pin.sha256;
    }) (lib.filterAttrs (_: pin: pin.enable) pins);
    withReplacements = selected: pkgs.callPackage ../lib/patched-sources.nix {
      inherit root;
      sources = stockSources;
      replacements = selected;
    };
    sources = withReplacements replacements;
    # A filtered source is a coercible attribute set, not a flake package.
    # Keep the selected-source derivation when present; materialise stock otherwise.
    asSourcePackage = src:
      if lib.isDerivation src
      then src
      else pkgs.runCommand "retirement-stock-packwiz-source" {} ''
        mkdir -p "$out"
        cp -r ${src}/. "$out/"
      '';
    makeModpacks = selectedSources: lib.makeScope pkgs.newScope (scope: {
      inherit packwiz;
      sources = selectedSources;

      server = scope.callPackage ./server.nix {};
      client = scope.callPackage ./client.nix {};
      modrinth = scope.callPackage ./modrinth.nix {};
    });
    modpacks = makeModpacks sources;
    stock = makeModpacks stockSources;
    # Exercise index and side transformations without a Gradle build or downloads.
    dummy = "retirement fixture, not a Minecraft mod\n";
    fixture = pkgs.writeText "fixture.jar" dummy;
    fixtureReplacement = {source = fixture; sha256 = builtins.hashString "sha256" dummy;};
    fixtureSources = withReplacements {voxy = fixtureReplacement; create = fixtureReplacement;};
    pack = builtins.fromTOML (builtins.readFile ../../packwiz/pack.toml);
    # The server launcher is unfree; the same nixpkgs, so the same glibc as pkgs.
    serverPkgs = import inputs.nixpkgs {
      inherit system;
      overlays = [inputs.nix-minecraft.overlay];
      config.allowUnfreePredicate = pkg: lib.elem (lib.getName pkg) ["minecraft-server" "neoforge"];
    };
    bench = pkgs.callPackage ./bench.nix {
      clientPack = modpacks.client;
      serverPack = modpacks.server;
      # Same launcher as nix/minecraft.nix runs for the real server.
      serverLauncher = serverPkgs.neoforgeServers."neoforge-${builtins.replaceStrings ["."] ["_"] "${pack.versions.minecraft}-${pack.versions.neoforge}"}".override {jre_headless = serverPkgs.jdk25_headless;};
      bootstrapGeneral = (pkgs.callPackage ../bootstrap {domain = "bench.invalid";}).settings.General;
    };
  in {
    # gamescope and MangoHud are Linux-only.
    apps = lib.optionalAttrs pkgs.stdenv.isLinux {
      bench = {
        type = "app";
        program = "${bench}/bin/bench";
        meta.description = "Client benchmark harness (scripts/bench/main.py)";
      };
    };

    packages = lib.optionalAttrs pkgs.stdenv.isLinux {inherit bench;} // {
      inherit packwiz;
      voxy-memory = candidates.voxy;
      create-panel = candidates.create;
      packwiz-source = asSourcePackage sources.src;
      modpack-client-stock = stock.client;
      modpack-server-stock = stock.server;
      modrinth-stock = stock.modrinth;
      modpack-server = modpacks.server;
      modpack-client = modpacks.client;
      modrinth = modpacks.modrinth;
      default = modpacks.client;
    };

    checks.patched-metadata = pkgs.runCommand "retirement-patched-metadata-check" {
      nativeBuildInputs = [pkgs.python3];
    } ''
      diff -r ${stockSources.src} ${asSourcePackage stockSources.src}
      python3 ${../lib/check-patched-sources.py} ${asSourcePackage stockSources.src} ${asSourcePackage fixtureSources.src}
      touch "$out"
    '';
    checks.modpacks = pkgs.callPackage ../lib/check-modpacks.nix {
      inherit sources;
      inherit (modpacks) client server;
    };
  };
}
