import com.sun.management.ThreadMXBean;
import it.unimi.dsi.fastutil.ints.Int2ObjectMap;
import it.unimi.dsi.fastutil.ints.Int2ObjectOpenHashMap;
import it.unimi.dsi.fastutil.longs.Long2IntMap;
import it.unimi.dsi.fastutil.longs.Long2IntOpenHashMap;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.management.ManagementFactory;
import java.util.Locale;
import java.util.Random;

/** Exercises the actual patched Sable predicate without constructing a world or OpenGL context. */
public final class CheckSableLighting {
  private static final MethodHandle CANDIDATE;
  private static volatile int sink;
  static {
    try {
      var method = Class.forName(
          "dev.ryanhcode.sable.neoforge.compatibility.flywheel.SableFlywheelLightStorage")
          .getDeclaredMethod("containsTrackedSection", Int2ObjectMap.class, long.class);
      method.setAccessible(true);
      CANDIDATE = MethodHandles.lookup().unreflect(method);
    } catch (ReflectiveOperationException e) {
      throw new ExceptionInInitializerError(e);
    }
  }

  private static boolean candidate(Int2ObjectMap<Long2IntMap> scenes, long section) throws Throwable {
    return (boolean) CANDIDATE.invokeExact(scenes, section);
  }

  private static boolean original(Int2ObjectMap<Long2IntMap> scenes, long section) {
    return scenes.values().stream().anyMatch(map -> map.containsKey(section));
  }

  private static void require(Int2ObjectMap<Long2IntMap> scenes, long key, boolean expected)
      throws Throwable {
    if (candidate(scenes, key) != expected) throw new AssertionError("Membership for " + key);
  }

  private static void regression() throws Throwable {
    Int2ObjectMap<Long2IntMap> scenes = new Int2ObjectOpenHashMap<>();
    require(scenes, 0, false);
    scenes.put(0, new Long2IntOpenHashMap());
    scenes.put(7, new Long2IntOpenHashMap());
    for (long key : new long[] {0, -1, Long.MIN_VALUE, Long.MAX_VALUE}) {
      scenes.get(7).put(key, 0);
      require(scenes, key, true);
      scenes.get(0).put(key, 12);
      scenes.get(7).remove(key);
      require(scenes, key, true);
      scenes.get(0).remove(key);
      require(scenes, key, false);
    }
    Random random = new Random(5800);
    for (int n = 0; n < 10000; n++) {
      int scene = random.nextInt(16);
      long key = random.nextInt(128) - 64;
      var map = scenes.computeIfAbsent(scene, ignored -> new Long2IntOpenHashMap());
      if (random.nextBoolean()) map.put(key, n); else map.remove(key);
      if (candidate(scenes, key) != original(scenes, key))
        throw new AssertionError("Differential scene membership at mutation " + n);
      if (n % 17 == 0) scenes.remove(scene);
    }
    scenes.clear();
    require(scenes, 0, false);
    System.out.println("PASS: actual patched predicate; empty, boundary, duplicate, removal and 10000 mutation cases");
  }

  private static void run(Int2ObjectMap<Long2IntMap> scenes, boolean patched, int count)
      throws Throwable {
    int hits = 0;
    for (int i = 0; i < count; i++) {
      long key = i & 255;
      if (patched ? candidate(scenes, key) : original(scenes, key)) hits++;
    }
    sink = hits;
  }

  private static void benchmark() throws Throwable {
    ThreadMXBean bean = (ThreadMXBean) ManagementFactory.getThreadMXBean();
    if (!bean.isThreadAllocatedMemorySupported())
      throw new IllegalStateException("Thread allocation measurement unavailable");
    bean.setThreadAllocatedMemoryEnabled(true);
    long thread = Thread.currentThread().threadId();
    for (int sceneCount : new int[] {1, 8, 64}) {
      Int2ObjectMap<Long2IntMap> scenes = new Int2ObjectOpenHashMap<>();
      for (int s = 0; s < sceneCount; s++) {
        var map = new Long2IntOpenHashMap();
        for (int key = s; key < 128; key += sceneCount) map.put(key, key);
        scenes.put(s, map);
      }
      run(scenes, false, 200000);
      run(scenes, true, 200000);
      for (int pair = 0; pair < 5; pair++) {
        for (int order = 0; order < 2; order++) {
          boolean patched = ((pair + order) & 1) == 1;
          long bytes = bean.getThreadAllocatedBytes(thread);
          long start = System.nanoTime();
          run(scenes, patched, 1000000);
          long elapsed = System.nanoTime() - start;
          long allocated = bean.getThreadAllocatedBytes(thread) - bytes;
          System.out.printf(Locale.ROOT, "scenes=%d pair=%d %s ns/op=%.3f B/op=%.3f hits=%d%n",
              sceneCount, pair, patched ? "patched" : "original", elapsed / 1000000.0,
              allocated / 1000000.0, sink);
        }
      }
    }
  }

  public static void main(String[] args) throws Throwable {
    regression();
    if (args.length == 1 && args[0].equals("--benchmark")) benchmark();
    else if (args.length != 0) throw new IllegalArgumentException("Optional argument: --benchmark");
  }
}
