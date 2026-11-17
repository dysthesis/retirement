{...}: {
  perSystem = {
    pkgs,
    lib,
    ...
  }: let
    packwiz = pkgs.callPackage ./packwiz.nix {};
    sources = pkgs.callPackage ../lib/packwiz.nix {root = ../../packwiz;};
    modpacks = lib.makeScope pkgs.newScope (scope: {
      inherit sources packwiz;

      server = scope.callPackage ./server.nix {};
      client = scope.callPackage ./client.nix {};
      modrinth = scope.callPackage ./modrinth.nix {};
    });
  in {
    packages = {
      inherit packwiz;
      modpack-server = modpacks.server;
      modpack-client = modpacks.client;
      modrinth = modpacks.modrinth;
      default = modpacks.client;
    };

    checks.modpacks = pkgs.callPackage ../lib/check-modpacks.nix {
      inherit sources;
      inherit (modpacks) client server;
    };
  };
}
