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
    inherit (config.retirement) bootstrap discord;
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

    options.retirement.bootstrap = {
      domain = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        description = "Host that serves the game and the Packwiz tree at /modpack/. Null disables the bootstrap.";
      };

      package = lib.mkOption {
        type = lib.types.nullOr lib.types.package;
        readOnly = true;
        description = "Prism Launcher import ZIP for this server's address and port.";
        default =
          if bootstrap.domain == null
          then null
          else
            pkgs.callPackage ./bootstrap {
              inherit (bootstrap) domain;
              port = home.serverProperties.server-port;
            };
      };
    };

    config = {
      nixpkgs.overlays = [
        inputs.nix-minecraft.overlay
      ];

      # Simple Voice Chat listens separately from the Minecraft TCP socket.
      networking.firewall.allowedUDPPorts = lib.optional (minecraft.enable && home.enable && home.openFirewall) 24454;

      # Content waits for restart. Do not silently change the live listener.
      # Stop the JVM before a listener change.
      system.preSwitchChecks.minecraftEndpoint = ''
        case "$2" in
          switch|test|dry-activate|check)
            state=$(${config.systemd.package}/bin/systemctl show minecraft-server-retirement-home.service --property=ActiveState --value)
            if [ "$state" != inactive ] && [ "$state" != failed ] &&
               ! ${pkgs.gnugrep}/bin/grep -Fxq ${lib.escapeShellArg "server-port=${toString home.serverProperties.server-port}"} ${lib.escapeShellArg "${minecraft.dataDir}/retirement-home/server.properties"}; then
              echo "Minecraft port change requires maintenance: stop minecraft-server-retirement-home.service, switch, then start it if autoStart is disabled." >&2
              exit 1
            fi
            ;;
        esac
      '';

      # Spark's async-profiler needs access to native kernel call frames.
      boot.kernel.sysctl."kernel.perf_event_paranoid" = lib.mkDefault 1;

      systemd.services.minecraft-server-retirement-home = {
        # Neither restart nor reload: nix-minecraft's reload replaces files beneath the running JVM.
        restartIfChanged = lib.mkForce false;
        reloadIfChanged = lib.mkForce false;

        # Limit the native async-profiler dependency to this service.
        environment.LD_LIBRARY_PATH = lib.makeLibraryPath [pkgs.stdenv.cc.cc.lib];

        serviceConfig = {
          LoadCredential = lib.mkIf discord.enable ["discord-env:${discord.environmentFile}"];
          # glibc uses AF_NETLINK before DNS resolution.
          RestrictAddressFamilies = lib.mkForce ["AF_UNIX" "AF_INET" "AF_INET6" "AF_NETLINK"];
        };
      };

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

          extraStartPre =
            ''
              # Don't move biome boundaries in installations that already generated chunks.
              biome=defaultconfigs/biolith/general.json
              if [[ ! -e "$biome" ]]; then
                install -Dm644 "${modpack}/$biome" "$biome"
              fi
            ''
            + lib.optionalString discord.enable ''
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

          # Back up config/ before stopping an old deployment that still manages the whole directory.
          files =
            lib.genAttrs modpack.configPaths (path: "${modpack}/${path}")
            // {
              "server-icon.png" = "${../assets/icons/retirement-home-icon-64.png}";
              # NeoForge bootstrap discovery requires a real mods directory.
              mods = "${modpack}/mods";
            };
        };
      };
    };
  };
}
