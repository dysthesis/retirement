import com.sun.tools.attach.VirtualMachine;
import java.io.PrintWriter;
import java.lang.instrument.Instrumentation;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;

/** Attach after EMI finishes loading in a joined client, or after server startup. */
public final class CheckPackIntegrations {
  public static void main(String[] args) throws Exception {
    VirtualMachine vm = VirtualMachine.attach(args[0]);
    try {
      vm.loadAgent(args[1], args[2]);
    } finally {
      vm.detach();
    }
  }

  public static void agentmain(String output, Instrumentation instrumentation) throws Exception {
    ClassLoader loader = null;
    Class<?> clientType = null;
    for (Class<?> type : instrumentation.getAllLoadedClasses()) {
      if (type.getName().equals("net.minecraft.client.Minecraft")) {
        loader = type.getClassLoader();
        clientType = type;
        break;
      }
      if (type.getName().equals("net.minecraft.server.MinecraftServer"))
        loader = type.getClassLoader();
    }
    if (loader == null) throw new AssertionError("No native Minecraft runtime loaded");
    ClassLoader gameLoader = loader;
    Class<?> client = clientType;
    Object runtime =
        client == null
            ? loader
                .loadClass("net.neoforged.neoforge.server.ServerLifecycleHooks")
                .getMethod("getCurrentServer")
                .invoke(null)
            : client.getMethod("getInstance").invoke(null);
    if (runtime == null) throw new AssertionError("No running Minecraft runtime");
    CompletableFuture.runAsync(
            () -> {
              try (PrintWriter out = new PrintWriter(output)) {
                try {
                  Object world =
                      client == null
                          ? runtime.getClass().getMethod("overworld").invoke(runtime)
                          : client.getField("level").get(runtime);
                  if (world == null)
                    throw new AssertionError("Join a world before checking integrations");
                  checkSeasons(gameLoader, world, out);
                  checkOreProcessing(gameLoader, world, out);
                  checkWashingFluids(gameLoader, out);
                  if (client != null) checkViewer(gameLoader, out);
                } catch (Throwable failure) {
                  failure.printStackTrace(out);
                  throw new RuntimeException(failure);
                }
              } catch (java.io.FileNotFoundException failure) {
                throw new RuntimeException(failure);
              }
            },
            (Executor) runtime)
        .get(120, TimeUnit.SECONDS);
  }

  private static void checkSeasons(ClassLoader loader, Object world, PrintWriter out)
      throws Exception {
    Class<?> level = loader.loadClass("net.minecraft.world.level.Level");
    Object seasonState =
        loader
            .loadClass("sereneseasons.api.season.SeasonHelper")
            .getMethod("getSeasonState", level)
            .invoke(null, world);
    Object expected =
        loader
            .loadClass("sereneseasons.api.season.ISeasonState")
            .getMethod("getSeason")
            .invoke(seasonState);
    Object event =
        loader
            .loadClass("com.github.thedeathlycow.thermoo.api.season.ThermooSeasonEvents")
            .getField("GET_CURRENT_SEASON")
            .get(null);
    Object invoker =
        loader.loadClass("net.fabricmc.fabric.api.event.Event").getMethod("invoker").invoke(event);
    Optional<?> actual =
        (Optional<?>)
            loader
                .loadClass(
                    "com.github.thedeathlycow.thermoo.api.season.ThermooSeasonEvents$CurrentSeasonCallback")
                .getMethod("getCurrentSeason", level)
                .invoke(invoker, world);
    String expectedName = ((Enum<?>) expected).name();
    if (actual.isEmpty() || !((Enum<?>) actual.get()).name().equals(expectedName)) {
      throw new AssertionError(
          "Thermoo season " + actual + " does not match Serene Seasons " + expectedName);
    }
    out.println("PASS: Thermoo follows Serene Seasons " + expectedName);
  }

  private static void checkOreProcessing(ClassLoader loader, Object world, PrintWriter out)
      throws Exception {
    requireCrushingOutput(
        loader, world, "minecraft:diamond_ore", "spelunkery:rough_diamond", 1, out);
    requireCrushingOutput(
        loader, world, "spelunkery:andesite_diamond_ore", "spelunkery:rough_diamond", 2, out);
  }

  private static void requireCrushingOutput(
      ClassLoader loader, Object world, String inputId, String outputId, int count, PrintWriter out)
      throws Exception {
    Class<?> stackType = loader.loadClass("net.minecraft.world.item.ItemStack");
    Object input =
        stackType
            .getConstructor(loader.loadClass("net.minecraft.world.level.ItemLike"))
            .newInstance(item(loader, inputId));
    Object recipeInput =
        loader
            .loadClass("net.minecraft.world.item.crafting.SingleRecipeInput")
            .getConstructor(stackType)
            .newInstance(input);
    Class<?> createTypes = loader.loadClass("com.simibubi.create.AllRecipeTypes");
    Object crushing = createTypes.getField("CRUSHING").get(null);
    Optional<?> match =
        (Optional<?>)
            createTypes
                .getMethod(
                    "find",
                    loader.loadClass("net.minecraft.world.item.crafting.RecipeInput"),
                    loader.loadClass("net.minecraft.world.level.Level"))
                .invoke(crushing, recipeInput, world);
    Object holder =
        match.orElseThrow(() -> new AssertionError("No Create crushing recipe for " + inputId));
    Object recipe = holder.getClass().getMethod("value").invoke(holder);
    List<?> results = (List<?>) recipe.getClass().getMethod("getRollableResults").invoke(recipe);
    Object first = results.getFirst();
    Object output = first.getClass().getMethod("getStack").invoke(first);
    if (stackType.getMethod("getItem").invoke(output) != item(loader, outputId)
        || (int) stackType.getMethod("getCount").invoke(output) != count
        || ((Number) first.getClass().getMethod("getChance").invoke(first)).doubleValue() != 1.0) {
      throw new AssertionError("Unexpected guaranteed crushing output for " + inputId);
    }
    out.println("PASS: Create crushes " + inputId + " into " + count + " " + outputId);
  }

  private static void checkWashingFluids(ClassLoader loader, PrintWriter out) throws Exception {
    Class<?> location = loader.loadClass("net.minecraft.resources.ResourceLocation");
    Class<?> fluidType = loader.loadClass("net.minecraft.world.level.material.Fluid");
    Class<?> fluidState = loader.loadClass("net.minecraft.world.level.material.FluidState");
    Class<?> registryType = loader.loadClass("net.minecraft.core.Registry");
    Object fluids =
        loader
            .loadClass("net.minecraft.core.registries.BuiltInRegistries")
            .getField("FLUID")
            .get(null);
    Class<?> createTags = loader.loadClass("com.simibubi.create.AllTags$AllFluidTags");
    Object splashing = createTags.getField("FAN_PROCESSING_CATALYSTS_SPLASHING").get(null);
    var matches = createTags.getMethod("matches", fluidState);
    for (String name :
        List.of(
            "minecraft:water",
            "streamsreflowing:stream",
            "streamsreflowing:flowing_stream",
            "minecraft:lava")) {
      Object id = location.getMethod("parse", String.class).invoke(null, name);
      Object fluid =
          ((Optional<?>) registryType.getMethod("getOptional", location).invoke(fluids, id))
              .orElseThrow();
      Object state = fluidType.getMethod("defaultFluidState").invoke(fluid);
      boolean accepted = (boolean) matches.invoke(splashing, state);
      boolean shouldWash = !name.equals("minecraft:lava");
      if (accepted != shouldWash) {
        throw new AssertionError(
            "Unexpected Create washing eligibility for " + name + ": " + accepted);
      }
      out.println("PASS: Create washing " + (accepted ? "accepts " : "rejects ") + name);
    }
  }

  private static void checkViewer(ClassLoader loader, PrintWriter out) throws Exception {
    if (!(boolean)
        loader
            .loadClass("dev.emi.emi.runtime.EmiReloadManager")
            .getMethod("isLoaded")
            .invoke(null)) {
      throw new IllegalStateException(
          "Wait for EMI to finish loading before checking recipe integrations");
    }
    Object manager =
        loader.loadClass("dev.emi.emi.api.EmiApi").getMethod("getRecipeManager").invoke(null);
    requireVisibleRecipe(
        loader, manager, "getRecipesByInput", "minecraft:diamond_ore", "create:crushing", out);
    requireVisibleRecipe(
        loader,
        manager,
        "getRecipesByOutput",
        "cataclysm:ignitium_elytra_chestplate",
        "cataclysm:weapon_infusion",
        out);
  }

  private static void requireVisibleRecipe(
      ClassLoader loader,
      Object manager,
      String lookup,
      String itemId,
      String categoryId,
      PrintWriter out)
      throws Exception {
    Class<?> stack = loader.loadClass("dev.emi.emi.api.stack.EmiStack");
    Object ingredient =
        stack
            .getMethod("of", loader.loadClass("net.minecraft.world.level.ItemLike"))
            .invoke(null, item(loader, itemId));
    Iterable<?> recipes =
        (Iterable<?>)
            loader
                .loadClass("dev.emi.emi.api.recipe.EmiRecipeManager")
                .getMethod(lookup, stack)
                .invoke(manager, ingredient);
    Class<?> recipeType = loader.loadClass("dev.emi.emi.api.recipe.EmiRecipe");
    Class<?> categoryType = loader.loadClass("dev.emi.emi.api.recipe.EmiRecipeCategory");
    for (Object recipe : recipes) {
      Object category = recipeType.getMethod("getCategory").invoke(recipe);
      if (categoryType.getMethod("getId").invoke(category).toString().equals(categoryId)) {
        out.println("PASS: EMI exposes " + categoryId + " for " + itemId);
        return;
      }
    }
    throw new AssertionError("EMI has no " + categoryId + " recipe for " + itemId);
  }

  private static Object item(ClassLoader loader, String name) throws Exception {
    Class<?> location = loader.loadClass("net.minecraft.resources.ResourceLocation");
    Object id = location.getMethod("parse", String.class).invoke(null, name);
    Object registry =
        loader
            .loadClass("net.minecraft.core.registries.BuiltInRegistries")
            .getField("ITEM")
            .get(null);
    return ((Optional<?>)
            loader
                .loadClass("net.minecraft.core.Registry")
                .getMethod("getOptional", location)
                .invoke(registry, id))
        .orElseThrow();
  }
}
