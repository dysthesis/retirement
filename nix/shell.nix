{
  perSystem = {pkgs, ...}: {
    devShells.default = pkgs.mkShellNoCC {
      name = "retirement-dev";
      packages = with pkgs; [
        packwiz
        just
        jdk21
        gitMinimal
        jq

        nil
        statix
        deadnix
        alejandra
      ];
    };
  };
}
