{
  perSystem = {
    pkgs,
    self',
    ...
  }: {
    devShells.default = pkgs.mkShellNoCC {
      name = "retirement-dev";
      packages = with pkgs; [
        self'.packages.packwiz
        just
        jdk21
        gitMinimal
        jq
        python3Minimal

        nil
        statix
        deadnix
        alejandra
      ];
    };
  };
}
