{
  perSystem = {pkgs, ...}: {
    devShells.default = pkgs.mkShellNoCC {
      name = "retirement-dev";
      packages = with pkgs; [
        packwiz
        just

        nil
        statix
        deadnix
        alejandra
      ];
    };
  };
}
