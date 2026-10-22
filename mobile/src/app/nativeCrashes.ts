import { takePendingCrashes } from "../../modules/crash-log/src";
import { log } from "./Log";

/**
 * Report anything the last process died of.
 *
 * A native crash takes the VM with it, so JavaScript never runs again to write
 * anything about it — the handler that caught it could only leave a file
 * behind. This is the other half: read that file at launch, turn each entry
 * into an ordinary log line, and let them ride up with everything else.
 *
 * Its own module rather than part of Log, which everything imports: this one
 * reaches into a native module, and Log has to stay importable by the host test
 * run — it is the piece that must work when nothing else does.
 */
export async function reportNativeCrashes(): Promise<number> {
  try {
    const crashes = await takePendingCrashes();
    for (const crash of crashes) {
      log.write("error", "native", `${crash.type}: ${crash.message}`, {
        // The phone's clock at the moment it died, not now. A crash reported at
        // the next launch may be a week old, and that gap is the whole story.
        crashedAt: new Date(crash.at).toISOString(),
        thread: crash.thread,
        stack: crash.stack,
      });
    }
    if (crashes.length > 0) await log.flush();
    return crashes.length;
  } catch {
    // Android-only, and optional even there: a build without the module reports
    // no native crashes rather than failing to start.
    return 0;
  }
}
