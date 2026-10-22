package expo.modules.rawaudio

/**
 * The recorder's lifecycle, with the audio taken out.
 *
 * Four flags decide everything [WavRecorder] does — whether the microphone is
 * open, whether bytes are being written, whether closing a file should also
 * close the microphone, and which session a running thread belongs to — and
 * every bug this recorder has had was one of them disagreeing with another.
 * They were entangled with `AudioRecord`, which meant they could only be
 * exercised by holding a phone.
 *
 * So the rules live here, where a JVM test can drive them through sequences
 * nobody wants to perform by hand: stop while listening, record twice, a start
 * arriving while a stale thread is still winding down. The audio stays in
 * WavRecorder; this only decides what is allowed and what it means.
 *
 * Every transition returns what the caller must *do*, rather than leaving the
 * caller to re-derive it from the flags. That is the part that kept going
 * wrong.
 *
 * Mutators are synchronized because [fail] arrives from the capture thread,
 * while every other transition runs on the module queue. Reads stay lock-free
 * on the volatile fields.
 */
internal class SessionState {

    @Volatile
    var active = false
        private set

    @Volatile
    var recording = false
        private set

    /** The microphone outlives the file: stopping a capture leaves it open. */
    @Volatile
    var keepListening = false
        private set

    /**
     * Which session a capture thread belongs to.
     *
     * Rises on every retirement so a thread that has not noticed yet can tell
     * it is out of date — `active` cannot answer that, because the next session
     * sets it back to true.
     */
    @Volatile
    var generation = 0
        private set

    /** Open, and not writing. The state the rolling buffer runs in. */
    fun isListening(): Boolean = active && !recording

    /**
     * Begin holding the microphone without writing anything.
     *
     * Refuses when one is already open: two would fight over the device, and
     * the second would silently win the route.
     */
    @Synchronized
    fun beginListening() {
        check(!active) { "already listening" }
        keepListening = true
    }

    /**
     * Begin writing.
     *
     * Returns true when the microphone is already open and the recording should
     * start from the ring buffer, false when the caller has to open one. The
     * distinction is the pre-roll: the whole point of listening beforehand.
     */
    @Synchronized
    fun beginRecording(): Boolean {
        check(!recording) { "already recording" }
        if (active) {
            recording = true
            return true
        }
        keepListening = false
        return false
    }

    /**
     * Stop writing.
     *
     * Returns true when the microphone stays open — a capture ended while
     * listening continues, because crows call in bouts and the second call is
     * missed as easily as the first.
     */
    @Synchronized
    fun endRecording(): Boolean {
        check(recording) { "not recording" }
        recording = false
        return keepListening
    }

    /** Stop holding the microphone. Safe to call when it is not held. */
    @Synchronized
    fun endListening() {
        keepListening = false
        retire()
    }

    /**
     * Retire the current session, invalidating any thread still running in it.
     *
     * Returns the generation that has just been retired, for a caller that
     * wants to say which one it was waiting for.
     */
    @Synchronized
    fun retire(): Int {
        val retired = generation
        generation += 1
        active = false
        recording = false
        return retired
    }

    /**
     * Mark a freshly opened session live, and hand back its number.
     *
     * The thread compares it on every pass, so a stale one leaves whatever the
     * flags say afterwards.
     */
    @Synchronized
    fun open(writing: Boolean): Int {
        active = true
        recording = writing
        return generation
    }

    /**
     * The capture thread died — a revoked microphone, a dead audio server, a
     * full disk. The microphone is gone, so the session is over, however the
     * flags read: listening is no longer claimed and a new session may open.
     *
     * `recording` is deliberately left standing so a stop() can still pass its
     * own check and collect the file with the failure attached. `keepListening`
     * is not — a stop must not hand the session back to a thread that no
     * longer exists.
     *
     * Returns whether the thread still owned the session. A stale thread's
     * death means nothing and changes nothing.
     */
    @Synchronized
    fun fail(session: Int): Boolean {
        if (session != generation) return false
        keepListening = false
        active = false
        return true
    }

    /** Whether a thread holding this number still owns the session. */
    fun owns(session: Int): Boolean = session == generation
}
