import com.sun.tools.attach.VirtualMachine;
import java.io.PrintWriter;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.HashSet;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

/** Fabric 1.21.1: run `just check-client-repairs PID OUTPUT` after joining a world and EMI finishes loading. */
public final class CheckClientRepairs {
    public static void main(String[] args) throws Exception {
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(args[1], args[2]);
        } finally {
            vm.detach();
        }
    }

    public static void agentmain(String output, Instrumentation instrumentation) throws Exception {
        Class<?> client = Arrays.stream(instrumentation.getAllLoadedClasses())
            .filter(type -> type.getName().equals("net.minecraft.class_310"))
            .findFirst().orElseThrow();
        ClassLoader loader = client.getClassLoader();
        Executor executor = (Executor) client.getMethod("method_1551").invoke(null);
        CompletableFuture.runAsync(() -> {
            try (PrintWriter out = new PrintWriter(output)) {
                check(loader, out);
            } catch (Exception failure) {
                throw new RuntimeException(failure);
            }
        }, executor).get(60, TimeUnit.SECONDS);
    }

    private static void check(ClassLoader loader, PrintWriter out) throws Exception {
        Class<?> api = loader.loadClass("dev.emi.emi.api.EmiApi");
        Class<?> recipe = loader.loadClass("dev.emi.emi.api.recipe.EmiRecipe");
        Object manager = api.getMethod("getRecipeManager").invoke(null);
        Iterable<?> recipes = (Iterable<?>) loader.loadClass("dev.emi.emi.api.recipe.EmiRecipeManager")
            .getMethod("getRecipes").invoke(manager);
        var ids = new HashSet<String>();
        Method recipeId = recipe.getMethod("getId");
        for (Object entry : recipes) ids.add(String.valueOf(recipeId.invoke(entry)));

        Class<?> armor = loader.loadClass("net.minecraft.class_1738");
        Class<?> tool = loader.loadClass("net.minecraft.class_1831");
        Class<?> ingredientType = loader.loadClass("net.minecraft.class_1856");
        Class<?> registryEntry = loader.loadClass("net.minecraft.class_6880");
        Iterable<?> items = (Iterable<?>) loader.loadClass("dev.emi.emi.EmiPort")
            .getMethod("getItemRegistry").invoke(null);
        int checked = 0;
        for (Object item : items) {
            Object ingredient = null;
            if (armor.isInstance(item)) {
                Object material = registryEntry.getMethod("comp_349")
                    .invoke(armor.getMethod("method_7686").invoke(item));
                ingredient = ((Supplier<?>) loader.loadClass("net.minecraft.class_1741")
                    .getMethod("comp_2301").invoke(material)).get();
            } else if (tool.isInstance(item)) {
                Object material = tool.getMethod("method_8022").invoke(item);
                ingredient = loader.loadClass("net.minecraft.class_1832")
                    .getMethod("method_8023").invoke(material);
            }
            if (ingredient == null || (boolean) ingredientType.getMethod("method_8103").invoke(ingredient)) continue;
            if (((Object[]) ingredientType.getMethod("method_8105").invoke(ingredient)).length != 0) continue;
            String id = (String) loader.loadClass("dev.emi.emi.EmiUtil")
                .getMethod("subId", loader.loadClass("net.minecraft.class_1792")).invoke(null, item);
            if (!ids.contains("emi:/anvil/repairing/tool/" + id)
                    || !ids.contains("emi:/grindstone/repairing/" + id)) {
                throw new AssertionError("Empty material tag hid same-item repair recipes for " + id);
            }
            out.println(id + ": anvil and grindstone repairs present");
            checked++;
        }
        if (checked == 0) throw new AssertionError("No unresolved repair-material tag was exercised");
        out.println("PASS: " + checked + " unresolved material tags preserve same-item repairs");
    }
}
