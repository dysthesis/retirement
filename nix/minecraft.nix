{
  self,
  inputs,
  ...
}: {
  flake.nixosModules.default = {pkgs, ...}: let
    modpack = pkgs.fetchPackwizModpack {
      src = "${self}/packwiz";
      packHash = "sha256-BJp2GA3kK642HEjFVaMYE7sCrIsmFuJXA245OooySio=";
    };
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

        package = pkgs.fabricServers.fabric-1_21_11;

        jvmOpts = "-Xms8G -Xmx10G";

        serverProperties = {
          server-port = 25565;
          max-players = 10;
          motd = "<INSERT MOTD HERE>";
          difficulty = "hard";
          white-list = true;
        };

        symlinks.mods = "${modpack}/mods";
        files.config = "${modpack}/config";
      };
    };
  };
}
