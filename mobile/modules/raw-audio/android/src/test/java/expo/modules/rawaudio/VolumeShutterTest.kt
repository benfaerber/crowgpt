package expo.modules.rawaudio

import android.view.KeyEvent
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The volume-shutter rules, driven through what a Bluetooth camera remote
 * actually sends: a HID keyboard press of VOLUME_UP, with the same
 * DOWN/repeat/UP shape as any held key.
 */
class VolumeShutterTest {

    @Test
    fun `one press is one toggle`() {
        assertTrue(
            VolumeShutter.isToggle(KeyEvent.KEYCODE_VOLUME_UP, KeyEvent.ACTION_DOWN, 0),
        )
        assertFalse(
            "the UP half of the same press must not toggle again",
            VolumeShutter.isToggle(KeyEvent.KEYCODE_VOLUME_UP, KeyEvent.ACTION_UP, 0),
        )
    }

    @Test
    fun `a held key does not machine-gun the recorder`() {
        assertFalse(
            VolumeShutter.isToggle(KeyEvent.KEYCODE_VOLUME_UP, KeyEvent.ACTION_DOWN, 3),
        )
    }

    @Test
    fun `both halves of a two-button remote count`() {
        // Which key the remote sends depends on which vendor's idea of
        // "Android mode" it implements, so both are the shutter.
        for (key in intArrayOf(
            KeyEvent.KEYCODE_VOLUME_UP,
            KeyEvent.KEYCODE_VOLUME_DOWN,
        )) {
            assertTrue(VolumeShutter.claims(key))
            assertTrue(VolumeShutter.isToggle(key, KeyEvent.ACTION_DOWN, 0))
        }
    }

    @Test
    fun `every other key is left alone`() {
        // The handler runs for every key the Activity sees; consuming one
        // that is not the shutter would eat Back or a keyboard.
        for (key in intArrayOf(
            KeyEvent.KEYCODE_BACK,
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
            KeyEvent.KEYCODE_ENTER,
            KeyEvent.KEYCODE_VOLUME_MUTE,
        )) {
            assertFalse(VolumeShutter.claims(key))
            assertFalse(VolumeShutter.isToggle(key, KeyEvent.ACTION_DOWN, 0))
        }
    }

    @Test
    fun `a disabled or module-less shutter drops the press instead of crashing`() {
        VolumeShutterState.enabled = false
        VolumeShutterState.onPress = null
        var pressed = 0
        // What RawAudioPackage's handler does, minus the Activity.
        fun deliver(keyCode: Int) {
            if (!VolumeShutterState.enabled || !VolumeShutter.claims(keyCode)) return
            VolumeShutterState.onPress?.invoke(keyCode)
        }
        deliver(KeyEvent.KEYCODE_VOLUME_UP)
        VolumeShutterState.enabled = true
        deliver(KeyEvent.KEYCODE_VOLUME_UP)
        VolumeShutterState.onPress = { pressed += 1 }
        deliver(KeyEvent.KEYCODE_VOLUME_UP)
        assertTrue(pressed == 1)
        VolumeShutterState.enabled = false
        VolumeShutterState.onPress = null
    }
}
