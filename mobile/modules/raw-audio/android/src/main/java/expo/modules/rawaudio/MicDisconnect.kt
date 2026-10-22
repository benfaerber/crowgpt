package expo.modules.rawaudio

import android.media.AudioDeviceInfo

/**
 * A microphone the recorder is on, or was on until its session died.
 *
 * [endedAtMs] is null while the session is still open, and otherwise the moment
 * it failed — on the same clock as the `nowMs` handed to
 * [MicDisconnect.shouldAnnounce]. A session the recordist ended on purpose is
 * not a route in play at all and never appears here: nothing was lost.
 */
data class MicRoute(val type: Int, val endedAtMs: Long?)

/**
 * Whether a set of just-removed inputs is worth saying out loud.
 *
 * The Rode fell off mid-session on 2026-07-31 and the only alert was a passer-by
 * shouting that it had hit the ground. Everything after that was recorded on the
 * wrong microphone, and nothing on a phone in a bag could have said so.
 *
 * The whole difficulty is restraint. Bluetooth and USB inputs appear and vanish
 * constantly — a watch connecting, a car dock, an earbud case opening — and a
 * cue that fires on all of them is noise that gets tuned out within a walk,
 * which is worse than silence because it is silence you have stopped noticing.
 * So the only removal worth a word is the one that took *this session's* mic.
 *
 * WHY THIS TAKES A LIST. The first version asked the recorder one question —
 * "which microphone is the open session on" — and got null in the case it was
 * built for, because losing the microphone is what *ends* the session. The
 * capture thread's read fails within half a second of the unplug, `SessionState.fail`
 * closes the session, and the app then swaps onto the phone mic; whichever of
 * those wins the race against the device callback, the answer to "which mic is
 * open" is no longer the mic that fell off. So the recorder now reports every
 * route in play — the live one and the one that just died under it — and the
 * removal only has to match one of them.
 *
 * Kept free of Android state so it can be tested on the JVM, like [Heartbeat]
 * and [PreRoll]. The int constants are compile-time literals, so the stubbed
 * android.jar in unit tests never has to answer for them.
 */
class MicDisconnect {

    private var lastAnnouncedAt: Long? = null

    /**
     * @param removedTypes `AudioDeviceInfo.getType()` of everything just unplugged.
     * @param routes every microphone in play — see [MicRoute]. Empty when no
     *   session is open and none has just died.
     * @param nowMs a monotonic clock — `SystemClock.uptimeMillis` in production.
     */
    fun shouldAnnounce(removedTypes: List<Int>, routes: List<MicRoute>, nowMs: Long): Boolean {
        if (!worthAnnouncing(removedTypes, routes, nowMs)) return false
        // A loose connector can flap several times a second. The first word is
        // the useful one; the fifth in three seconds is just shouting.
        lastAnnouncedAt?.let { if (nowMs - it < QUIET_MS) return false }
        lastAnnouncedAt = nowMs
        return true
    }

    private fun worthAnnouncing(
        removedTypes: List<Int>,
        routes: List<MicRoute>,
        nowMs: Long,
    ): Boolean = routes.any { route ->
        // The built-in mic does not fall off a jacket. If it ever disappears the
        // problem is not one a person can fix by picking something up, and
        // onSessionFailure is the honest channel for it.
        route.type != AudioDeviceInfo.TYPE_BUILTIN_MIC &&
            stillCounts(route, nowMs) &&
            removedTypes.contains(route.type)
    }

    /**
     * A dead session's microphone is only news for a moment.
     *
     * It has to outlive the session because the session dies first, and it must
     * not outlive it by long: a session that failed at the start of the walk
     * would otherwise make every unplug for the rest of it say "microphone
     * disconnected", which is the noise this class exists to avoid.
     */
    private fun stillCounts(route: MicRoute, nowMs: Long): Boolean {
        val endedAt = route.endedAtMs ?: return true
        return nowMs - endedAt < GRACE_MS
    }

    private companion object {
        const val QUIET_MS = 5_000L
        const val GRACE_MS = 10_000L
    }
}
