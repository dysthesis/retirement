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

  flake.nixosModules.default = {config, lib, pkgs, ...}: let
    discord = config.retirement.discord;
    modpack = self.packages.${pkgs.stdenv.hostPlatform.system}.modpack-server;
    pack = builtins.fromTOML (builtins.readFile ../packwiz/pack.toml);
  in {
    imports = [
      inputs.nix-minecraft.nixosModules.minecraft-servers
    ];

    options.retirement.discord = {
      enable = lib.mkEnableOption "SDLink runtime credential injection";

      tokenFile = lib.mkOption {
        type = lib.types.str;
        description = "Absolute runtime path to a file containing the Discord bot token.";
      };

      channelId = lib.mkOption {
        type = lib.types.strMatching "[0-9]{17,20}";
        description = "Discord text channel ID (not a secret).";
      };
    };

    config = {
      nixpkgs.overlays = [
        inputs.nix-minecraft.overlay
      ];

      systemd.services.minecraft-server-retirement-home.serviceConfig.LoadCredential =
        lib.mkIf discord.enable ["discord-bot-token:${discord.tokenFile}"];

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

          # nix-minecraft copies the modpack before running extraStartPre.
          # Keep decrypted credentials out of Nix evaluation and the store.
          extraStartPre = lib.mkIf discord.enable ''
            ${lib.getExe pkgs.python3} ${./render-discord.py} ${lib.escapeShellArg discord.channelId}
          '';

          serverProperties = {
            server-port = 25565;
            max-players = 10;
            motd = "<INSERT MOTD HERE>";
            difficulty = "hard";
            white-list = true;
            online-mode = true;
          };

          files = {
            "config" = "${modpack}/config";
            "server-icon.png" = ../assets/icons/retirement-home-icon-512.png;
            # NeoForge bootstrap discovery requires a real mods directory.
            mods = "${modpack}/mods";
          };
        };
      };
    };
  };
}
