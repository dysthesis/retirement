{
  perSystem = {pkgs, ...}: {
    devShells.default = pkgs.mkShellNoCC {
      name = "retirement-dev";
      packages = with pkgs; [
        packwiz
        just
        jdk21
        gitMinimal

        nil
        statix
        deadnix
        alejandra
      ];
    };
  };
}
