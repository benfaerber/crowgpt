package expo.modules.rawaudio

import android.media.ToneGenerator
import android.view.KeyEvent

/**
 * What the headset button means, kept apart from MediaSession so it runs on
 * the JVM. The constants below are compile-time ints, which is what makes that
 * possible without an emulator.
 */
object HeadsetButton {

    /**
     * Every key that reads as "the button" across headsets. AirPods send
     * PLAY_PAUSE; wired remotes send HEADSETHOOK; some Bluetooth stacks split
     * the pair into PLAY and PAUSE depending on what they believe is happening.
     */
    private val TOGGLE_KEYS = setOf(
        KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
        KeyEvent.KEYCODE_MEDIA_PLAY,
        KeyEvent.KEYCODE_MEDIA_PAUSE,
        KeyEvent.KEYCODE_HEADSETHOOK,
    )

    /** Whether this key belongs to the trigger and must not reach another app. */
    fun claims(keyCode: Int): Boolean = keyCode in TOGGLE_KEYS

    /**
     * Whether this event is one press. DOWN only, and only the first repeat:
     * a held button auto-repeats, and each UP arrives as its own event — either
     * would turn one tap into a start immediately followed by a stop.
     */
    fun isToggle(keyCode: Int, action: Int, repeatCount: Int): Boolean =
        claims(keyCode) && action == KeyEvent.ACTION_DOWN && repeatCount == 0

    /** Two presses closer together than this came from one tap. */
    const val PRESS_WINDOW_MS = 400L
}

/**
 * One tap, one toggle, however many ways the phone reports it.
 *
 * [HeadsetButton.isToggle] already filters the KeyEvent path down to a single
 * DOWN. It cannot help with the other path: a press can also arrive as a
 * transport control through `onPlay`/`onPause`, and some Bluetooth stacks
 * deliver *both* for one tap, or send play and pause as a pair. Each of those
 * emits its own toggle, so a single press starts a recording and immediately
 * stops it — which from the outside is a button that did nothing at all.
 *
 * That is the shape of "it works sometimes": not a button that is ignored, but
 * one that fires an even number of times.
 *
 * A gate across both paths rather than a fix to either, because the duplicate
 * is not within a path — it is between them, and neither can see the other.
 */
class PressGate(private val windowMs: Long = HeadsetButton.PRESS_WINDOW_MS) {
    private var lastAt: Long? = null

    /** @return true when this press should count as a new one. */
    fun accept(now: Long): Boolean {
        val last = lastAt
        if (last != null && now - last < windowMs) return false
        lastAt = now
        return true
    }
}

/**
 * The answers the phone can give from inside a bag.
 *
 * Pitch is the whole interface: started is a bright beep, stopped a lower
 * blend, and failed the network error trill — the one sound everybody already
 * knows means "that did not happen". Failed exists because a press the phone
 * silently ignored looks identical to a recording, right up until the capture
 * list is checked at home.
 *
 * The last two repeat: the heartbeat says them every few seconds so listening,
 * recording and silently-dead are three different sounds rather than one
 * silence. LISTENING is the quietest thing here — a 40 ms tick, because an
 * hour of pocket listening says it hundreds of times — and RECORDING is a
 * double beep that cannot be mistaken for it.
 */
enum class Cue(val tone: Int, val toneMs: Int, val vibration: LongArray) {
    STARTED(ToneGenerator.TONE_PROP_BEEP, 150, longArrayOf(0, 80)),
    STOPPED(ToneGenerator.TONE_PROP_NACK, 400, longArrayOf(0, 80, 140, 80)),
    FAILED(ToneGenerator.TONE_SUP_ERROR, 900, longArrayOf(0, 450)),
    LISTENING(ToneGenerator.TONE_PROP_ACK, 150, longArrayOf(0, 40)),
    RECORDING(ToneGenerator.TONE_PROP_BEEP2, 250, longArrayOf(0, 40, 120, 40));

    companion object {
        fun from(name: String): Cue? =
            values().firstOrNull { it.name.equals(name, ignoreCase = true) }
    }
}
