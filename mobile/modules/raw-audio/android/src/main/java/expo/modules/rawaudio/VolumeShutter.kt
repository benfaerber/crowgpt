package expo.modules.rawaudio

import android.view.KeyEvent

/**
 * What a Bluetooth camera remote means, kept apart from the Activity so it
 * runs on the JVM — the same split as [HeadsetButton], for the same reason.
 *
 * A shutter remote is not a media device: it enrolls as a HID keyboard
 * hardwired to send VOLUME_UP, because that is the key every phone camera app
 * treats as its shutter. The remote cannot be told to send anything else —
 * there is nothing to configure on it — so the app meets it where it is and
 * claims the volume keys instead.
 *
 * Both volume keys, not just up: the two-button remotes split themselves into
 * an "iOS" and an "Android" half, and which half sends which key varies by
 * vendor. While the trigger setting is on, neither key changes the volume
 * inside the app — that is the documented price on the switch.
 */
object VolumeShutter {

    private val SHUTTER_KEYS = setOf(
        KeyEvent.KEYCODE_VOLUME_UP,
        KeyEvent.KEYCODE_VOLUME_DOWN,
    )

    /** Whether this key belongs to the shutter and must not adjust the volume. */
    fun claims(keyCode: Int): Boolean = keyCode in SHUTTER_KEYS

    /**
     * Whether this event is one press: DOWN only, and only the first — a held
     * key auto-repeats, and each UP is its own event, either of which would
     * turn one press into a start immediately followed by a stop.
     */
    fun isToggle(keyCode: Int, action: Int, repeatCount: Int): Boolean =
        claims(keyCode) && action == KeyEvent.ACTION_DOWN && repeatCount == 0
}

/**
 * The channel between the Activity's key events and the module.
 *
 * Two objects with no reference to each other need it: the key handler is
 * created by [RawAudioPackage] when the Activity is, the module by the JS
 * runtime, and neither can reach the other except through here. `enabled`
 * mirrors the trigger setting and is asserted by JS at startup and on every
 * change; `onPress` is the module's event emitter and dies with it, so a
 * press against a torn-down module goes nowhere rather than somewhere stale.
 */
object VolumeShutterState {
    @Volatile
    var enabled = false

    @Volatile
    var onPress: ((keyCode: Int) -> Unit)? = null
}
