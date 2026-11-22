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

  flake.nixosModules.default = {
    config,
    lib,
    pkgs,
    ...
  }: let
    discord = config.retirement.discord;
    minecraft = config.services.minecraft-servers;
    home = minecraft.servers.retirement-home;
    modpack = self.packages.${pkgs.stdenv.hostPlatform.system}.modpack-server;
    pack = builtins.fromTOML (builtins.readFile ../packwiz/pack.toml);
  in {
    imports = [
      inputs.nix-minecraft.nixosModules.minecraft-servers
    ];

    options.retirement.discord = {
      enable = lib.mkEnableOption "SDLink runtime credential injection";

      environmentFile = lib.mkOption {
        type = lib.types.strMatching "/.+";
        description = "Runtime path to a file containing DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID assignments.";
      };
    };

    config = {
      nixpkgs.overlays = [
        inputs.nix-minecraft.overlay
      ];

      # Simple Voice Chat listens separately from the Minecraft TCP socket.
      networking.firewall.allowedUDPPorts = lib.optional (minecraft.enable && home.enable && home.openFirewall) 24454;

      systemd.services.minecraft-server-retirement-home.serviceConfig.LoadCredential =
        lib.mkIf discord.enable ["discord-env:${discord.environmentFile}"];

      services.minecraft-servers = {
        enable = true;
        eula = true;

        servers.retirement-home = {
          enable = true;
          autoStart = true;
          openFirewall = true;

          # Java 25 enables C2ME's optional native-math module.
          package = pkgs.neoforgeServers."neoforge-${builtins.replaceStrings ["."] ["_"] "${pack.versions.minecraft}-${pack.versions.neoforge}"}".override {jre_headless = pkgs.jdk25_headless;};

          jvmOpts = "-Xms10G -Xmx12G";

          # nix-minecraft copies the modpack before running extraStartPre.
          # Keep decrypted credentials out of Nix evaluation and the store.
          extraStartPre = lib.mkIf discord.enable ''
            ${lib.getExe pkgs.python3} ${./render-discord-env.py}
          '';

          serverProperties = {
            server-port = 25565;
            max-players = 10;
            motd = "Retirement Home";
            difficulty = "hard";
            white-list = true;
            online-mode = true;
          };

          files = {
            "config" = "${modpack}/config";
            "server-icon.png" = ../assets/icons/retirement-home-icon-64.png;
            # NeoForge bootstrap discovery requires a real mods directory.
            mods = "${modpack}/mods";
          };
        };
      };
    };
  };
}
