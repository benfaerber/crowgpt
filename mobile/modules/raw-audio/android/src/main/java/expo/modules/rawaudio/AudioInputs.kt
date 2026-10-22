package expo.modules.rawaudio

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager

/**
 * Which microphone a capture actually uses.
 *
 * Android routes recording to whatever it considers the current input, and a
 * connected Bluetooth headset usually wins. For a phone call that is right; for
 * bioacoustics it is ruinous — the SCO path is narrowband and heavily processed,
 * so walking around with earbuds in silently turns every capture into an 8 kHz
 * speech-optimised recording of a bird call. The corpus is the product here, and
 * nothing in the UI would have shown it happening.
 *
 * So the built-in mic is pinned by default, and the preference is explicit
 * rather than inherited from whatever happens to be paired. An external mic
 * worth plugging in is a deliberate choice, so it is a deliberate setting.
 */
object AudioInputs {

    /** Pin the phone's own microphone, whatever else is connected. The default. */
    const val BUILT_IN = "builtin"

    /** Let Android route — including to a headset. Only if explicitly asked for. */
    const val AUTOMATIC = "auto"

    private const val TYPE_PREFIX = "type:"

    /**
     * A preference for a specific kind of input, e.g. `type:22` for a USB
     * headset.
     *
     * Deliberately keyed on device *type* rather than `AudioDeviceInfo.getId()`:
     * ids are assigned per connection, so a preference stored by id stops
     * matching the moment the mic is unplugged and plugged back in — which is
     * exactly when someone would notice it had silently reverted.
     */
    fun forType(type: Int): String = "$TYPE_PREFIX$type"

    /**
     * The preference naming a device, with the phone's own mic spelled the way
     * the rest of the app spells it.
     *
     * The built-in microphone has two names: [BUILT_IN], which is the pin the
     * settings list stores, and `type:15` from [forType], which is what
     * enumeration reports. They mean one device. Anything that *compares* a
     * route against a preference has to agree which spelling wins, and the
     * first thing that ever compared them did not — so the buffer reopened
     * itself on every input change, deciding each time that `type:15` was not
     * `builtin` and it had better switch. Four restarts in ninety seconds, each
     * one throwing away the pre-roll ring, and a capture that should have
     * reached back fifteen seconds reached back three.
     */
    fun preferenceFor(type: Int): String =
        if (type == AudioDeviceInfo.TYPE_BUILTIN_MIC) BUILT_IN else forType(type)

    fun list(context: Context): List<Map<String, Any?>> {
        val manager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        return manager.getDevices(AudioManager.GET_DEVICES_INPUTS)
            .filter { isRecordable(it.type) }
            .map { device ->
                mapOf(
                    "preference" to forType(device.type),
                    "type" to device.type,
                    "typeLabel" to RecordPathInspector.deviceLabel(device.type),
                    "name" to device.productName.toString(),
                    "isBuiltIn" to (device.type == AudioDeviceInfo.TYPE_BUILTIN_MIC),
                    "isExternal" to isExternal(device.type),
                )
            }
    }

    /**
     * The device to pin for a preference, and whether it is the one asked for.
     *
     * Falls back to the built-in mic when a requested input isn't connected: the
     * alternative is honouring "auto" by accident and recording through earbuds,
     * which is the failure this exists to prevent.
     *
     * `matched` is what makes that fallback visible. Pinning a USB microphone,
     * unplugging it and recording used to report `inputHonoured = true` — the
     * policy had honoured the *fallback*, and nothing in the capture said the
     * substitution had happened. A corpus half-recorded through a microphone
     * that was not attached is worse than one that admits which.
     */
    data class Chosen(val device: AudioDeviceInfo?, val matched: Boolean)

    fun choose(context: Context, preference: String?): Chosen {
        if (preference == AUTOMATIC) return Chosen(null, true)
        val manager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val inputs = manager.getDevices(AudioManager.GET_DEVICES_INPUTS)

        val requestedType = preference?.removePrefix(TYPE_PREFIX)?.toIntOrNull()
        if (requestedType != null) {
            inputs.firstOrNull { it.type == requestedType }
                ?.let { return Chosen(it, true) }
        }
        val builtin = inputs.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_MIC }
        // Asking for the built-in and getting it is a match; asking for
        // something else and getting it instead is not.
        return Chosen(builtin, requestedType == null)
    }

    /**
     * Inputs a person could actually record a bird with.
     *
     * An allowlist rather than an allow-everything-but: a Pixel 10 enumerates
     * REMOTE_SUBMIX (a virtual routing device) and ECHO_REFERENCE (the signal
     * the phone is *playing*, fed back for echo cancellation) among its inputs,
     * and both were being offered as microphones. Recording through the second
     * one captures the phone's own output.
     *
     * Android keeps adding virtual input types, so a denylist is a promise to
     * keep chasing them. This list is short because the set of things you can
     * clip to a jacket is short.
     */
    private fun isRecordable(type: Int): Boolean = when (type) {
        AudioDeviceInfo.TYPE_BUILTIN_MIC,
        AudioDeviceInfo.TYPE_WIRED_HEADSET,
        AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
        AudioDeviceInfo.TYPE_BLE_HEADSET,
        AudioDeviceInfo.TYPE_USB_DEVICE,
        AudioDeviceInfo.TYPE_USB_ACCESSORY,
        AudioDeviceInfo.TYPE_USB_HEADSET,
        AudioDeviceInfo.TYPE_LINE_ANALOG,
        AudioDeviceInfo.TYPE_LINE_DIGITAL,
        AudioDeviceInfo.TYPE_AUX_LINE,
        AudioDeviceInfo.TYPE_DOCK -> true
        else -> false
    }

    /** Something plugged in or paired, as opposed to the phone's own hardware. */
    private fun isExternal(type: Int): Boolean = when (type) {
        AudioDeviceInfo.TYPE_BUILTIN_MIC -> false
        AudioDeviceInfo.TYPE_TELEPHONY -> false
        else -> true
    }
}
