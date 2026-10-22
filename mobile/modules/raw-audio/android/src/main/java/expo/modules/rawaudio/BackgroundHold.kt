package expo.modules.rawaudio

/**
 * The wish for pocket listening, kept apart from whether it is granted.
 *
 * The bug this exists for: `setBackground` used to answer from the moment it
 * ran — `enabled && isListening()` — and a request landing while the session
 * was between a stop and a start was told no, once, with nothing to retry it.
 * Pocket listening then believed it was on while no foreground service held
 * the process, which is reapable, and on a backgrounded phone gets reaped —
 * taking the MediaSession and the earbud button with it.
 *
 * So the wish is remembered here, and [reassert] runs after every moment a
 * session (re)opens. A refusal stops being forever; it lasts until the next
 * open, which is exactly the moment the answer changes.
 *
 * The one asymmetry is deliberate, and it is [MicrophoneSwap]'s rule seen
 * from the other side: wanting the service while nothing is listening starts
 * nothing (a microphone service with no microphone is a notification about
 * nothing) but also STOPS nothing — mid-swap the service is alive over a
 * closed session on purpose, and stopping it here would end pocket listening
 * on every route change. Only "not wanted" stops the service.
 */
internal class BackgroundHold(
    /** A session is open — the only state in which the service may start. */
    private val listening: () -> Boolean,
    /** Whether the foreground service currently holds the permission. */
    private val serviceRunning: () -> Boolean,
    private val startService: () -> Unit,
    private val stopService: () -> Unit,
) {
    @Volatile
    private var wanted = false

    /**
     * Record the wish without acting on it.
     *
     * For `startListening`, which must start the service *before* the session
     * opens (Android denies a backgrounded app the microphone otherwise) and
     * so cannot go through [reassert]'s listening check.
     */
    fun expect(enabled: Boolean) {
        wanted = enabled
    }

    /** The setting changed. Returns whether the service now holds the mic. */
    fun set(enabled: Boolean): Boolean {
        wanted = enabled
        return reassert()
    }

    /**
     * Make the service match the wish, and say whether it now holds the mic.
     *
     * Run after every session (re)open — this is the repair the log line
     * `serviceHolding: false` used to only describe.
     */
    fun reassert(): Boolean {
        if (!wanted) {
            if (serviceRunning()) stopService()
            return false
        }
        if (!listening()) return false
        if (!serviceRunning()) startService()
        return true
    }
}
