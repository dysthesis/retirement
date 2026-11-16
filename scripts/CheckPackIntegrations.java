import com.sun.tools.attach.VirtualMachine;
import java.io.PrintWriter;
import java.lang.instrument.Instrumentation;
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
            if (type.getName().equals("net.minecraft.server.MinecraftServer")) loader = type.getClassLoader();
        }
        if (loader == null) throw new AssertionError("No native Minecraft runtime loaded");
        ClassLoader gameLoader = loader;
        Class<?> client = clientType;
        Object runtime = client == null
            ? loader.loadClass("net.neoforged.neoforge.server.ServerLifecycleHooks")
                .getMethod("getCurrentServer").invoke(null)
            : client.getMethod("getInstance").invoke(null);
        if (runtime == null) throw new AssertionError("No running Minecraft runtime");
        CompletableFuture.runAsync(() -> {
            try (PrintWriter out = new PrintWriter(output)) {
                try {
                    Object world = client == null ? runtime.getClass().getMethod("overworld").invoke(runtime)
                        : client.getField("level").get(runtime);
                    if (world == null) throw new AssertionError("Join a world before checking integrations");
                    checkSeasons(gameLoader, world, out);
                    if (client != null) checkViewer(gameLoader, out);
                } catch (Throwable failure) {
                    failure.printStackTrace(out);
                    throw new RuntimeException(failure);
                }
            } catch (java.io.FileNotFoundException failure) {
                throw new RuntimeException(failure);
            }
        }, (Executor) runtime).get(120, TimeUnit.SECONDS);
    }

    private static void checkSeasons(ClassLoader loader, Object world, PrintWriter out) throws Exception {
        Class<?> level = loader.loadClass("net.minecraft.world.level.Level");
        Object seasonState = loader.loadClass("sereneseasons.api.season.SeasonHelper")
            .getMethod("getSeasonState", level).invoke(null, world);
        Object expected = loader.loadClass("sereneseasons.api.season.ISeasonState")
            .getMethod("getSeason").invoke(seasonState);
        Object event = loader.loadClass("com.github.thedeathlycow.thermoo.api.season.ThermooSeasonEvents")
            .getField("GET_CURRENT_SEASON").get(null);
        Object invoker = loader.loadClass("net.fabricmc.fabric.api.event.Event")
            .getMethod("invoker").invoke(event);
        Optional<?> actual = (Optional<?>) loader.loadClass(
                "com.github.thedeathlycow.thermoo.api.season.ThermooSeasonEvents$CurrentSeasonCallback")
            .getMethod("getCurrentSeason", level).invoke(invoker, world);
        String expectedName = ((Enum<?>) expected).name();
        if (actual.isEmpty() || !((Enum<?>) actual.get()).name().equals(expectedName)) {
            throw new AssertionError("Thermoo season " + actual + " does not match Serene Seasons " + expectedName);
        }
        out.println("PASS: Thermoo follows Serene Seasons " + expectedName);
    }

    private static void checkViewer(ClassLoader loader, PrintWriter out) throws Exception {
        if (!(boolean) loader.loadClass("dev.emi.emi.runtime.EmiReloadManager")
                .getMethod("isLoaded").invoke(null)) {
            throw new IllegalStateException("Wait for EMI to finish loading before checking recipe integrations");
        }
        Object manager = loader.loadClass("dev.emi.emi.api.EmiApi").getMethod("getRecipeManager").invoke(null);
        requireVisibleRecipe(loader, manager, "getRecipesByInput", "minecraft:diamond_ore", "create:crushing", out);
        requireVisibleRecipe(loader, manager, "getRecipesByOutput", "cataclysm:ignitium_elytra_chestplate",
            "cataclysm:weapon_infusion", out);
    }

    private static void requireVisibleRecipe(ClassLoader loader, Object manager, String lookup,
            String itemId, String categoryId, PrintWriter out) throws Exception {
        Class<?> stack = loader.loadClass("dev.emi.emi.api.stack.EmiStack");
        Object ingredient = stack.getMethod("of", loader.loadClass("net.minecraft.world.level.ItemLike"))
            .invoke(null, item(loader, itemId));
        Iterable<?> recipes = (Iterable<?>) loader.loadClass("dev.emi.emi.api.recipe.EmiRecipeManager")
            .getMethod(lookup, stack).invoke(manager, ingredient);
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
        Object registry = loader.loadClass("net.minecraft.core.registries.BuiltInRegistries").getField("ITEM").get(null);
        return ((Optional<?>) loader.loadClass("net.minecraft.core.Registry")
            .getMethod("getOptional", location).invoke(registry, id)).orElseThrow();
    }
}
