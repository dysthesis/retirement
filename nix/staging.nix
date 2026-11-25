# Switches stage content without touching the running JVM; port changes need explicit maintenance.
{
  pkgs,
  self,
}:
pkgs.testers.runNixOSTest {
  name = "retirement-staging";
  node.pkgsReadOnly = false;
  nodes.machine = {
    lib,
    pkgs,
    ...
  }: {
    imports = [self.nixosModules.default];
    config = {
      nixpkgs.config.allowUnfree = true;
      environment.systemPackages = [pkgs.netcat-openbsd];
      virtualisation = {
        memorySize = 2048;
        cores = 2;
      };
      services.minecraft-servers = {
        dataDir = "/srv/minecraft";
        managementSystem = {
          tmux.enable = false;
          systemd-socket.enable = true;
        };
        servers.retirement-home = {
          autoStart = lib.mkForce true;
          jvmOpts = lib.mkForce "-Xms128M -Xmx1024M";
          # The staging test exercises systemd semantics, not modpack content.
          package = lib.mkForce (pkgs.vanillaServers.vanilla-1_21_1.override {
            jre_headless = pkgs.jdk25_headless;
          });
          files = lib.mkForce {};
          serverProperties = {
            motd = lib.mkOverride 80 "Original";
            view-distance = 2;
            simulation-distance = 2;
            online-mode = lib.mkForce false;
          };
        };
      };
      specialisation = {
        staged.configuration.services.minecraft-servers.servers.retirement-home.serverProperties.motd = lib.mkForce "Staged";
        moved.configuration.services.minecraft-servers.servers.retirement-home.serverProperties = {
          motd = lib.mkForce "Moved";
          server-port = lib.mkForce 25566;
        };
      };
    };
  };
  testScript = ''
    start_all()
    unit = "minecraft-server-retirement-home.service"
    properties = "/srv/minecraft/retirement-home/server.properties"
    machine.wait_for_unit(unit)
    machine.wait_for_open_port(25565)
    base = machine.succeed("readlink -f /run/current-system").strip()
    staged = base + "/specialisation/staged"
    moved = base + "/specialisation/moved"
    invocation = machine.succeed(f"systemctl show {unit} --property=InvocationID --value")

    with subtest("content stays staged without restarting or rewriting live properties"):
        machine.succeed(f"{staged}/bin/switch-to-configuration switch")
        assert machine.succeed(f"systemctl show {unit} --property=InvocationID --value") == invocation
        machine.succeed(f"grep -Fx 'motd=Original' {properties}")
        machine.wait_for_open_port(25565)
        staged_system = machine.succeed("readlink -f /run/current-system").strip()

    with subtest("port change fails before activation while the old JVM is running"):
        machine.fail(f"{moved}/bin/switch-to-configuration switch")
        assert machine.succeed("readlink -f /run/current-system").strip() == staged_system
        assert machine.succeed(f"systemctl show {unit} --property=InvocationID --value") == invocation
        machine.wait_for_open_port(25565)
        machine.fail("nc -z 127.0.0.1 25566")

    with subtest("explicit maintenance advances the JVM and its listener together"):
        machine.succeed(f"systemctl stop {unit}")
        machine.wait_until_fails("nc -z 127.0.0.1 25565")
        machine.succeed(f"{moved}/bin/switch-to-configuration switch")
        machine.wait_for_unit(unit)
        machine.wait_for_open_port(25566)
        machine.fail("nc -z 127.0.0.1 25565")
        machine.succeed(f"grep -Fx 'motd=Moved' {properties}")
        machine.succeed(f"grep -Fx 'server-port=25566' {properties}")
        assert machine.succeed(f"systemctl show {unit} --property=InvocationID --value") != invocation
  '';
}
