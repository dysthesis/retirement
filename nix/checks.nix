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
    checks.minecraft = pkgs.testers.runNixOSTest {
      name = "retirement";
      node.pkgsReadOnly = false;
      globalTimeout = 1200;

      nodes.server = {config, ...}: {
        imports = [self.nixosModules.default];
        nixpkgs.config.allowUnfreePredicate = pkg: lib.getName pkg == "minecraft-server";

        assertions = [
          {
            assertion = config.services.minecraft-servers.servers.retirement.package.version == "${pack.versions.minecraft}-fabric-${pack.versions.fabric}";
            message = "retirement: packwiz requires ${pack.versions.minecraft}-fabric-${pack.versions.fabric}, but the server is ${config.services.minecraft-servers.servers.retirement.package.version}";
          }
        ];
        # Fixed seed makes biome coverage reproducible.
        services.minecraft-servers.servers.retirement.serverProperties.level-seed = "86204277";

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
        server = cfg.servers.retirement;
        settings = pkgs.writeText "retirement-check.json" (builtins.toJSON {
          log = "${cfg.dataDir}/retirement/logs/latest.log";
          tmux = "${pkgs.tmux}/bin/tmux -S ${lib.escapeShellArg (server.managementSystem.tmux.socketPath "retirement")}";
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
