{
  self,
  inputs,
  ...
}: {
  perSystem = {
    pkgs,
    system,
    ...
  }: {
    _module.args = {
      pkgs = import inputs.nixpkgs {
        inherit system;
        overlays = [inputs.nix-minecraft.overlay];
      };

      mkModpack = side: packHash: let
        pack = builtins.fromTOML (builtins.readFile ../packwiz/pack.toml);
      in
        (pkgs.fetchPackwizModpack {
          src = "${self}/packwiz";
          inherit side packHash;
        }).overrideAttrs (_: {
          # Fixed-output cache keys otherwise ignore changed source files.
          name = "${pack.name}-${pack.version}-${side}-${builtins.hashFile "sha256" ../packwiz/pack.toml}";
        });
    };
  };

  flake.nixosModules.default = {pkgs, ...}: let
    modpack = self.packages.${pkgs.stdenv.hostPlatform.system}.modpack-server;
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

      servers.retirement = {
        enable = true;
        autoStart = true;
        openFirewall = true;

        # C2ME's bundled native module requires Java 25.
        package = pkgs.fabricServers.fabric-1_21_1.override {jre_headless = pkgs.jdk25_headless;};

        jvmOpts = "-Xms8G -Xmx10G";

        serverProperties = {
          server-port = 25565;
          max-players = 10;
          motd = "<INSERT MOTD HERE>";
          difficulty = "hard";
          white-list = true;
        };

        files."config" = "${modpack}/config";
        symlinks.mods = "${modpack}/mods";
      };
    };
  };
}
