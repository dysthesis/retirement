import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import me.lucko.spark.proto.SparkSamplerProtos.SamplerData;
import me.lucko.spark.proto.SparkSamplerProtos.StackTraceNode;
import me.lucko.spark.proto.SparkSamplerProtos.ThreadNode;

/** Run with Spark 1.10.124 on the classpath; percentages are inclusive thread time, not FPS. */
public final class InspectSpark {
  private static final Map<String, String> TARGETS = Map.ofEntries(
      Map.entry("lighting", "SableFlywheelLightStorage.updateLightSections"),
      Map.entry("flywheel_wait", "WaitGroup.await"),
      Map.entry("sandstorm", "SandstormEffects.tickSandstormParticles"),
      Map.entry("weather", "WeatherProviderWithDefault.atPositionOrDefault"),
      Map.entry("particles", "ParticleEngine.tick"),
      Map.entry("async_wait", "TaskHelper.waitForCompletion"),
      Map.entry("boilers", "BoilerData.tick"),
      Map.entry("acoustics", "SoundPhysics.processSound"),
      Map.entry("particle_move", "Particle.sable$moveWithSubLevels"),
      Map.entry("stripes", "BlockStripeFeature.place"));

  private static double total(List<Double> times) {
    return times.stream().mapToDouble(Double::doubleValue).sum();
  }

  private static double inclusive(ThreadNode thread, List<Integer> roots, String target) {
    double result = 0;
    for (int ref : roots) {
      StackTraceNode node = thread.getChildren(ref);
      String method = node.getClassName() + "." + node.getMethodName();
      // Stop at the first matching ancestor: recursive occurrences must not double-count.
      result += method.contains(target) ? total(node.getTimesList())
          : inclusive(thread, node.getChildrenRefsList(), target);
    }
    return result;
  }

  private static void selfTest() {
    var leaf = StackTraceNode.newBuilder().setClassName("test.Target").setMethodName("run")
        .addTimes(2).build();
    var recursive = leaf.toBuilder().clearTimes().addTimes(3).addChildrenRefs(0).build();
    var thread = ThreadNode.newBuilder().setName("test").addTimes(5)
        .addChildren(leaf).addChildren(recursive).addChildrenRefs(1).build();
    if (inclusive(thread, thread.getChildrenRefsList(), "Target.run") != 3
        || inclusive(thread, thread.getChildrenRefsList(), "missing") != 0)
      throw new AssertionError("Inclusive recursion accounting");
    System.out.println("PASS: inclusive recursion accounting");
  }

  public static void main(String[] args) throws Exception {
    if (args.length == 1 && args[0].equals("--self-test")) {
      selfTest();
      return;
    }
    if (args.length == 0) throw new IllegalArgumentException("Pass raw .sparkprofile paths");
    for (String filename : args) {
      var profile = SamplerData.parseFrom(Files.readAllBytes(Path.of(filename)));
      var metadata = profile.getMetadata();
      System.out.printf(Locale.ROOT, "%s engine=%s interval_us=%d duration_s=%.3f threads=%d%n",
          Path.of(filename).getFileName(), metadata.getSamplerEngine(), metadata.getInterval(),
          (metadata.getEndTime() - metadata.getStartTime()) / 1000.0, profile.getThreadsCount());
      for (ThreadNode thread : profile.getThreadsList()) {
        double denominator = total(thread.getTimesList());
        if (denominator == 0) continue;
        for (var target : TARGETS.entrySet()) {
          double value = inclusive(thread, thread.getChildrenRefsList(), target.getValue());
          if (value > 0) System.out.printf(Locale.ROOT, "  %s\t%s\t%.4f%%\t%.3f/%.3f ms%n",
              thread.getName(), target.getKey(), 100 * value / denominator, value, denominator);
        }
      }
    }
  }
}
