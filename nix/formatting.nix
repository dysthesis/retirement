{inputs, ...}: {
  imports = [inputs.treefmt-nix.flakeModule];
  perSystem = _: {
    treefmt = {
      projectRootFile = "flake.nix";
      programs = {
        alejandra.enable = true;
        black.enable = true;
        pyright.enable = true;
        taplo.enable = true;
        google-java-format.enable = true;
        shellcheck.enable = true;
        shfmt.enable = true;
      };
    };
  };
}
