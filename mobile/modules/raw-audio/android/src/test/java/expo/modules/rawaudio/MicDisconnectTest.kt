package expo.modules.rawaudio

import android.media.AudioDeviceInfo
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The cue has to fire on the one removal that matters and stay quiet for every
 * other one. Both halves are load-bearing: a cue that misses the Rode falling
 * off is the bug this exists to fix, and a cue that speaks whenever a watch
 * disconnects is the reason someone stops listening to it before the mic ever
 * falls.
 *
 * The session-is-already-dead cases below are the ones that were missing when
 * this shipped silent. Every test here passed, and every one of them handed the
 * decider a live session — which is the state a phone whose microphone has just
 * been pulled out is never in.
 */
class MicDisconnectTest {

    private val usb = AudioDeviceInfo.TYPE_USB_HEADSET
    private val wired = AudioDeviceInfo.TYPE_WIRED_HEADSET
    private val builtin = AudioDeviceInfo.TYPE_BUILTIN_MIC

    /** The mic an open session is on. */
    private fun live(type: Int) = listOf(MicRoute(type, endedAtMs = null))

    /** The mic a session died on, at [at] on the same clock as `nowMs`. */
    private fun died(type: Int, at: Long) = listOf(MicRoute(type, endedAtMs = at))

    @Test
    fun `the mic this session is on going away is worth saying`() {
        assertTrue(MicDisconnect().shouldAnnounce(listOf(usb), live(usb), nowMs = 0))
    }

    @Test
    fun `some other device disconnecting is not`() {
        // A watch, a car dock, an earbud case — none of them are the mic.
        assertFalse(MicDisconnect().shouldAnnounce(listOf(wired), live(usb), nowMs = 0))
    }

    @Test
    fun `it still fires when the mic leaves alongside other devices`() {
        assertTrue(MicDisconnect().shouldAnnounce(listOf(wired, usb), live(usb), nowMs = 0))
    }

    @Test
    fun `no session and none just dead means nothing was lost`() {
        assertFalse(MicDisconnect().shouldAnnounce(listOf(usb), emptyList(), nowMs = 0))
    }

    @Test
    fun `the built-in mic is never announced`() {
        // It cannot fall off a jacket, so "microphone disconnected" would send
        // someone hunting for something on the ground that is not there.
        assertFalse(MicDisconnect().shouldAnnounce(listOf(builtin), live(builtin), nowMs = 0))
    }

    @Test
    fun `the session dying with the microphone is the case this is for`() {
        // What actually happens on an unplug: the read fails, the session
        // closes, and only then does the device callback arrive. Asking for a
        // live route here is asking for the one state that cannot exist.
        assertTrue(
            MicDisconnect().shouldAnnounce(listOf(usb), died(usb, at = 0), nowMs = 300),
        )
    }

    @Test
    fun `a session that died a minute ago is not this removal`() {
        assertFalse(
            MicDisconnect().shouldAnnounce(listOf(usb), died(usb, at = 0), nowMs = 60_000),
        )
    }

    @Test
    fun `the swap onto the phone mic does not swallow the loss`() {
        // The app reopens the buffer on the built-in mic the moment the Rode
        // goes, so both routes are in play by the time this is asked: a live
        // one that is not news and a dead one that is.
        val routes = listOf(MicRoute(builtin, endedAtMs = null), MicRoute(usb, endedAtMs = 0))
        assertTrue(MicDisconnect().shouldAnnounce(listOf(usb), routes, nowMs = 400))
    }

    @Test
    fun `a flapping connector is announced once, not five times`() {
        val decider = MicDisconnect()
        assertTrue(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 0))
        assertFalse(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 200))
        assertFalse(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 4_999))
    }

    @Test
    fun `but a later disconnection is announced again`() {
        val decider = MicDisconnect()
        assertTrue(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 0))
        assertTrue(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 5_000))
    }

    @Test
    fun `a suppressed repeat does not restart the quiet window`() {
        // Otherwise a connector flapping every second stays muted forever: each
        // ignored bounce would push the window out and the cue would never
        // recover, which is the failure mode of a naive debounce.
        val decider = MicDisconnect()
        assertTrue(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 0))
        assertFalse(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 1_000))
        assertFalse(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 2_000))
        assertTrue(decider.shouldAnnounce(listOf(usb), live(usb), nowMs = 5_000))
    }
}
