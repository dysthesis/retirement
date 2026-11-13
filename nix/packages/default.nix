{self, ...}: {
  perSystem = {
    pkgs,
    lib,
    mkModpack,
    ...
  }: let
    modpacks = lib.makeScope pkgs.newScope (scope: {
      inherit mkModpack;

      server = scope.callPackage ./server.nix {};
      client = scope.callPackage ./client.nix {};
    });
  in {
    packages = {
      modpack-server = modpacks.server;
      modpack-client = modpacks.client;
      modrinth = pkgs.callPackage ./modrinth.nix {inherit self;};
      default = modpacks.client;
    };
  };
}
