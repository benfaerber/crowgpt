package expo.modules.rawaudio

import android.view.KeyEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The press-counting rules, driven through the sequences a real button sends.
 *
 * One tap arrives as DOWN then UP, and a held button repeats the DOWN — so the
 * naive "any event toggles" reads a single tap as start-then-stop and throws
 * the capture away before it exists.
 */
class HeadsetButtonTest {

    @Test
    fun `one tap is one toggle`() {
        assertTrue(
            HeadsetButton.isToggle(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.ACTION_DOWN, 0),
        )
        assertFalse(
            "the UP half of the same tap must not toggle again",
            HeadsetButton.isToggle(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.ACTION_UP, 0),
        )
    }

    @Test
    fun `a held button does not machine-gun the recorder`() {
        assertFalse(
            HeadsetButton.isToggle(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.ACTION_DOWN, 3),
        )
    }

    @Test
    fun `every spelling of the button counts`() {
        // AirPods say PLAY_PAUSE, wired remotes say HEADSETHOOK, and some
        // Bluetooth stacks split the pair by what they think is playing.
        for (key in intArrayOf(
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
            KeyEvent.KEYCODE_MEDIA_PLAY,
            KeyEvent.KEYCODE_MEDIA_PAUSE,
            KeyEvent.KEYCODE_HEADSETHOOK,
        )) {
            assertTrue(HeadsetButton.isToggle(key, KeyEvent.ACTION_DOWN, 0))
            assertTrue(HeadsetButton.claims(key))
        }
    }

    @Test
    fun `skip-track is left alone`() {
        // Double-tap-to-skip was rejected as a design; claiming NEXT anyway
        // would quietly take it from whatever the session outranks.
        assertFalse(HeadsetButton.claims(KeyEvent.KEYCODE_MEDIA_NEXT))
        assertFalse(HeadsetButton.claims(KeyEvent.KEYCODE_MEDIA_PREVIOUS))
        assertFalse(HeadsetButton.isToggle(KeyEvent.KEYCODE_MEDIA_NEXT, KeyEvent.ACTION_DOWN, 0))
    }
}

class CueTest {

    @Test
    fun `the names JavaScript sends resolve`() {
        assertEquals(Cue.STARTED, Cue.from("started"))
        assertEquals(Cue.STOPPED, Cue.from("stopped"))
        assertEquals(Cue.FAILED, Cue.from("failed"))
    }

    @Test
    fun `an unknown cue is refused rather than guessed`() {
        // Playing *some* beep for a typo would confirm something that was
        // never asked, into the ears of someone who cannot see the screen.
        assertNull(Cue.from("armed"))
    }

    @Test
    fun `the three answers cannot be mistaken for each other`() {
        // Sound is the entire interface with the phone in a bag; two cues on
        // the same tone would collapse "recording" and "not recording" into
        // one beep.
        assertNotEquals(Cue.STARTED.tone, Cue.STOPPED.tone)
        assertNotEquals(Cue.STOPPED.tone, Cue.FAILED.tone)
        assertNotEquals(Cue.STARTED.tone, Cue.FAILED.tone)
    }

    @Test
    fun `every cue can also be felt`() {
        // The haptic fallback is degraded, not absent: each cue needs a
        // pattern, and each pattern starts with the zero-delay Android expects.
        for (cue in Cue.values()) {
            assertTrue(cue.vibration.isNotEmpty())
            assertEquals(0L, cue.vibration.first())
        }
    }
}
