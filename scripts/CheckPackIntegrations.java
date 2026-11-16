import com.sun.tools.attach.VirtualMachine;
import java.io.PrintWriter;
import java.lang.instrument.Instrumentation;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;

/** Attach to a disposable NeoForge 1.21.1 server after startup. */
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
        for (Class<?> type : instrumentation.getAllLoadedClasses()) {
            if (type.getName().equals("net.minecraft.server.MinecraftServer")) {
                loader = type.getClassLoader();
                break;
            }
        }
        if (loader == null) throw new AssertionError("No native Minecraft server loaded");
        ClassLoader gameLoader = loader;
        Object server = loader.loadClass("net.neoforged.neoforge.server.ServerLifecycleHooks")
            .getMethod("getCurrentServer").invoke(null);
        if (server == null) throw new AssertionError("No running server");
        CompletableFuture.runAsync(() -> {
            try (PrintWriter out = new PrintWriter(output)) {
                try {
                    checkSeasons(gameLoader, server, out);
                } catch (Throwable failure) {
                    failure.printStackTrace(out);
                    throw new RuntimeException(failure);
                }
            } catch (java.io.FileNotFoundException failure) {
                throw new RuntimeException(failure);
            }
        }, (Executor) server).get(120, TimeUnit.SECONDS);
    }

    private static void checkSeasons(ClassLoader loader, Object server, PrintWriter out) throws Exception {
        Class<?> level = loader.loadClass("net.minecraft.world.level.Level");
        Object world = server.getClass().getMethod("overworld").invoke(server);
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
}
