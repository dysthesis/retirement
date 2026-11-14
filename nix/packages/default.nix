{self, ...}: {
  perSystem = {
    pkgs,
    lib,
    mkModpack,
    ...
  }: let
    packwiz = pkgs.callPackage ./packwiz.nix {};
    modpacks = lib.makeScope pkgs.newScope (scope: {
      inherit mkModpack;

      server = scope.callPackage ./server.nix {};
      client = scope.callPackage ./client.nix {};
    });
  in {
    packages = {
      inherit packwiz;
      modpack-server = modpacks.server;
      modpack-client = modpacks.client;
      modrinth = pkgs.callPackage ./modrinth.nix {inherit self packwiz;};
      default = modpacks.client;
    };
  };
}
