package expo.modules.rawaudio

/**
 * Reopen the microphone session under a live [ListeningService].
 *
 * `stopListening` + `startListening` looks equivalent and is not: stopping
 * takes the foreground service down with the AudioRecord, and on Android 12+
 * a running foreground service is precisely what licenses a backgrounded app
 * to start one. The moment the service was gone the app was an ordinary
 * backgrounded process, the restart was refused with
 * `startForegroundService() not allowed`, and pocket listening died silently
 * on every input route change with music playing — earbuds resuming Spotify
 * was enough.
 *
 * So the one rule, held apart from the audio where a JVM test can enforce it:
 * a swap closes and reopens the *session* and never touches the service. Only
 * a swap that fails stands the service down, because after a failure nothing
 * is holding the microphone and a notification saying otherwise is the pocket
 * lie the service exists to prevent.
 *
 * The service genuinely not running (a foreground-only session) needs nothing
 * special here: the session still closes and reopens, standing down a service
 * that is not there is a no-op, and a failure still surfaces to the caller
 * rather than leaving a screen claiming to listen to a closed microphone.
 */
internal class MicrophoneSwap(
    /** A session is open and not writing — the only state a swap may touch. */
    private val listening: () -> Boolean,
    private val closeSession: () -> Unit,
    private val openSession: () -> Unit,
    /** Failure path only: the microphone is gone, so the notification must go. */
    private val standDownService: () -> Unit,
) {
    /**
     * Close the open session and reopen it, letting the audio policy route to
     * the input the caller re-resolved.
     *
     * Refuses when nothing is listening: there is no session to swap, and a
     * recording in progress must never be torn down for a route change.
     */
    fun swap() {
        check(listening()) { "nothing is listening — there is no session to swap" }
        try {
            closeSession()
            openSession()
        } catch (failure: Exception) {
            standDownService()
            throw failure
        }
    }
}
