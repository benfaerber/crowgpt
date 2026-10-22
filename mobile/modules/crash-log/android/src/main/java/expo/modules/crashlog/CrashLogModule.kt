package expo.modules.crashlog

import android.content.Context
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.json.JSONObject
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter

/**
 * The crash that kills the process, written down before it does.
 *
 * Everything else the app logs goes through JavaScript, which is fine right up
 * until the failure is native: a NullPointerException on a background thread
 * takes the process with it, and JS never runs again to write anything about
 * it. That is not a hypothetical failure mode here — the prepareAsync crash
 * that cost two afternoons was exactly this shape, and it was invisible because
 * `adb logcat` only exists while a cable is attached and is wiped by the
 * reinstall that follows every attempted fix.
 *
 * So the last thing this process does is append the stack to a file, and the
 * first thing the next one does is read it. Crossing a process boundary means
 * a file: nothing in memory survives, and there is no network at the moment a
 * VM is coming down.
 *
 * Deliberately tiny and deliberately dependency-free. Code that runs inside an
 * uncaught exception handler is running in a process that is already broken,
 * and anything clever it does — allocating, taking a lock, calling back into
 * JS — is a second crash on top of the one being reported.
 */
class CrashLogModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("CrashLog")

    OnCreate {
      install(appContext.reactContext?.applicationContext ?: return@OnCreate)
    }

    /**
     * Hand over what was caught, and forget it.
     *
     * Taken rather than read: an entry that survived being reported would be
     * reported again at every launch forever, and a log that repeats yesterday's
     * crash is worse than one that missed it.
     */
    AsyncFunction("takePendingAsync") {
      val file = crashFile ?: return@AsyncFunction emptyList<String>()
      if (!file.exists()) return@AsyncFunction emptyList<String>()
      val lines = file.readLines().filter { it.isNotBlank() }
      file.delete()
      return@AsyncFunction lines
    }
  }

  private var crashFile: File? = null

  private fun install(context: Context) {
    val file = File(context.filesDir, FILE_NAME)
    crashFile = file
    val previous = Thread.getDefaultUncaughtExceptionHandler()
    // Guard against installing twice — the module is created per JS runtime,
    // and a reload would otherwise chain a handler onto a handler.
    if (previous is Recorder) return
    Thread.setDefaultUncaughtExceptionHandler(Recorder(file, previous))
  }

  /**
   * Writes one line and then gets out of the way.
   *
   * Always delegates to whatever was there before — React Native installs its
   * own handler and the platform installs the one that shows the crash dialog.
   * Swallowing the exception here would turn a visible crash into a silent
   * freeze, which is a strictly worse thing to be debugging.
   */
  private class Recorder(
    private val file: File,
    private val previous: Thread.UncaughtExceptionHandler?,
  ) : Thread.UncaughtExceptionHandler {
    override fun uncaughtException(thread: Thread, error: Throwable) {
      try {
        val stack = StringWriter().also { error.printStackTrace(PrintWriter(it)) }.toString()
        val entry = JSONObject()
          .put("at", System.currentTimeMillis())
          .put("thread", thread.name)
          .put("type", error.javaClass.name)
          .put("message", error.message ?: "")
          .put("stack", stack.take(MAX_STACK))
        // Appended, because a crash loop produces several and the first one is
        // usually the interesting one. Capped by rewriting when it gets long:
        // this file must never be the reason storage runs out.
        val held = if (file.exists()) file.readLines().filter { it.isNotBlank() } else emptyList()
        val kept = (held + entry.toString()).takeLast(MAX_ENTRIES)
        file.writeText(kept.joinToString("\n"))
      } catch (_: Throwable) {
        // A failure while reporting a failure is not worth a third one.
      } finally {
        previous?.uncaughtException(thread, error)
      }
    }
  }

  private companion object {
    const val FILE_NAME = "native-crashes.jsonl"
    const val MAX_STACK = 8000
    const val MAX_ENTRIES = 20
  }
}
