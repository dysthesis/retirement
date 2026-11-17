{
  self,
  inputs,
  ...
}: {
  perSystem = {system, ...}: {
    _module.args = {
      pkgs = import inputs.nixpkgs {
        inherit system;
        overlays = [inputs.nix-minecraft.overlay];
      };
    };
  };

  flake.nixosModules.default = {pkgs, ...}: let
    modpack = self.packages.${pkgs.stdenv.hostPlatform.system}.modpack-server;
    pack = builtins.fromTOML (builtins.readFile ../packwiz/pack.toml);
  in {
    imports = [
      inputs.nix-minecraft.nixosModules.minecraft-servers
    ];

    nixpkgs.overlays = [
      inputs.nix-minecraft.overlay
    ];

    services.minecraft-servers = {
      enable = true;
      eula = true;

      servers.retirement-home = {
        enable = true;
        autoStart = true;
        openFirewall = true;

        # Java 25 enables C2ME's optional native-math module.
        package = pkgs.neoforgeServers."neoforge-${builtins.replaceStrings ["."] ["_"] "${pack.versions.minecraft}-${pack.versions.neoforge}"}".override {jre_headless = pkgs.jdk25_headless;};

        jvmOpts = "-Xms8G -Xmx10G";

        serverProperties = {
          server-port = 25565;
          max-players = 10;
          motd = "<INSERT MOTD HERE>";
          difficulty = "hard";
          white-list = true;
        };

        files."config" = "${modpack}/config";
        # NeoForge bootstrap discovery requires a real mods directory.
        files.mods = "${modpack}/mods";
      };
    };
  };
}
