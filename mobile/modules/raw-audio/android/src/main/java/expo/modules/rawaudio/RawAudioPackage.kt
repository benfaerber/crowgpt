package expo.modules.rawaudio

import android.content.Context
import android.view.KeyEvent
import expo.modules.core.interfaces.Package
import expo.modules.core.interfaces.ReactActivityHandler

/**
 * Hooks the Activity's key events without owning an Activity.
 *
 * `android/` is prebuild-managed, so MainActivity cannot carry code — but
 * expo's ReactActivityDelegateWrapper forwards onKeyDown/onKeyUp to every
 * ReactActivityHandler a Package provides, and autolinking discovers this
 * class by its `Package` import alone. That is the whole registration.
 *
 * This is the volume-shutter's delivery path, and it is narrower than the
 * headset button's on purpose: key events only reach an Activity that is in
 * the foreground with the screen on. A shutter remote is a tripod-and-frame
 * tool, so that is its actual use; pocket triggering stays with the
 * MediaSession path, which is built for it.
 *
 * Claimed keys are consumed on every action, not just the toggling DOWN —
 * an unconsumed repeat or UP would fall through to the system and change
 * the volume the press was supposed to be instead of.
 */
class RawAudioPackage : Package {
    override fun createReactActivityHandlers(
        activityContext: Context?,
    ): List<ReactActivityHandler> = listOf(
        object : ReactActivityHandler {
            override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
                if (!VolumeShutterState.enabled || !VolumeShutter.claims(keyCode)) return false
                if (VolumeShutter.isToggle(keyCode, KeyEvent.ACTION_DOWN, event?.repeatCount ?: 0)) {
                    VolumeShutterState.onPress?.invoke(keyCode)
                }
                return true
            }

            override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean =
                VolumeShutterState.enabled && VolumeShutter.claims(keyCode)

            override fun onKeyLongPress(keyCode: Int, event: KeyEvent?): Boolean =
                VolumeShutterState.enabled && VolumeShutter.claims(keyCode)
        },
    )
}
