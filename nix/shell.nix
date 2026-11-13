{
  perSystem = {pkgs, ...}: {
    devShells.default = pkgs.mkShellNoCC {
      name = "retirement-dev";
      packages = with pkgs; [
        packwiz

        nil
        statix
        deadnix
        alejandra
      ];
    };
  };
}
