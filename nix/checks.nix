# nix flake check -L requires a Linux/KVM builder with room for 12 GiB + 1 GiB guests.
{
  inputs,
  self,
  ...
}: {
  perSystem = {
    lib,
    system,
    ...
  }: let
    # Darwin must use a Linux builder, not silently skip the server check.
    pkgs = inputs.nixpkgs.legacyPackages.${lib.replaceStrings ["darwin"] ["linux"] system};
    pack = builtins.fromTOML (builtins.readFile ../packwiz/pack.toml);
  in {
    checks.discord-render = pkgs.runCommand "retirement-discord-render-check" {
      nativeBuildInputs = [pkgs.python3];
    } ''
      ${pkgs.python3}/bin/python3 ${../scripts/test-render-discord-env.py} \
        ${./render-discord-env.py} \
        ${../packwiz/config/simple-discord-link/simple-discord-link.toml}
      touch "$out"
    '';

    checks.bootstrap = let
      bootstrap = pkgs.callPackage ./bootstrap {domain = "mc.example.test";};
    in
      pkgs.runCommand "retirement-bootstrap-check" {
        nativeBuildInputs = [(pkgs.python3.withPackages (ps: [ps.pyqt6]))];
      } ''
        python3 ${./bootstrap/check.py} \
          ${bootstrap}/RetirementHome-bootstrap.zip \
          ${../packwiz/pack.toml} \
          ${lib.escapeShellArgs [bootstrap.domain bootstrap.clientJvmArgs]}
        touch "$out"
      '';

    checks.minecraft = pkgs.testers.runNixOSTest {
      name = "retirement";
      node.pkgsReadOnly = false;
      globalTimeout = 1200;

      nodes.server = {config, ...}: {
        imports = [self.nixosModules.default];
        nixpkgs.config.allowUnfreePredicate = pkg: lib.elem (lib.getName pkg) ["minecraft-server" "neoforge"];

        assertions = [
          {
            assertion = config.services.minecraft-servers.servers.retirement-home.package.version == "${pack.versions.minecraft}-${pack.versions.neoforge}";
            message = "retirement: packwiz requires ${pack.versions.minecraft}-${pack.versions.neoforge}, but the server is ${config.services.minecraft-servers.servers.retirement-home.package.version}";
          }
        ];
        # Fixed seed makes biome coverage reproducible.
        services.minecraft-servers.servers.retirement-home.serverProperties.level-seed = "86204277";

        # Keep the real JVM flags, mods, world generation, authentication and firewall.
        virtualisation = {
          memorySize = 12288;
          cores = 2;
          diskSize = 4096;
        };
      };
      nodes.client = {
        environment.systemPackages = [(pkgs.python3.withPackages (p: [p.mcstatus]))];
      };

      testScript = {nodes, ...}: let
        cfg = nodes.server.services.minecraft-servers;
        server = cfg.servers.retirement-home;
        settings = pkgs.writeText "retirement-check.json" (builtins.toJSON {
          log = "${cfg.dataDir}/retirement-home/logs/latest.log";
          tmux = "${pkgs.tmux}/bin/tmux -S ${lib.escapeShellArg (server.managementSystem.tmux.socketPath "retirement-home")}";
          status = lib.escapeShellArgs [
            "python"
            "${../scripts/check-minecraft-status.py}"
            "server:${toString server.serverProperties.server-port}"
            pack.versions.minecraft
            (toString server.serverProperties.max-players)
          ];
        });
      in
        lib.replaceStrings ["@settings@"] ["${settings}"]
        (builtins.readFile ../scripts/check-minecraft.py);
    };
  };
}
