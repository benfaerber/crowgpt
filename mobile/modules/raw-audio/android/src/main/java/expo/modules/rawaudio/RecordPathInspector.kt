package expo.modules.rawaudio

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.MediaRecorder
import android.media.audiofx.AudioEffect
import android.os.Build
import java.util.UUID

/**
 * Reads back what the audio policy actually did with a source request.
 *
 * `AudioRecord` will happily accept a source the device never advertises, so the
 * only trustworthy answer comes from the live recording configuration: it names
 * the source the policy really selected and lists the effects attached to the
 * record path. That turns "is AGC on?" from an inference about the noise floor
 * into a reading.
 *
 * Only valid while the session is recording, and an unprivileged app sees only
 * its own configurations — which is the one we want.
 */
class RecordPathInspector(context: Context) {

    data class Reading(
        val source: Int,
        val sourceLabel: String,
        val deviceLabel: String,
        val effects: List<String>,
        val clientEffects: List<String>,
    ) {
        val unprocessed: Boolean get() = effects.isEmpty() && clientEffects.isEmpty()
    }

    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    fun inspect(sessionId: Int): Reading? {
        val configuration = audioManager.activeRecordingConfigurations
            .firstOrNull { it.clientAudioSessionId == sessionId }
            ?: return null

        val effects = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            configuration.effects.map { effectLabel(it.type) }
        } else {
            emptyList()
        }
        val clientEffects = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            configuration.clientEffects.map { effectLabel(it.type) }
        } else {
            emptyList()
        }

        return Reading(
            source = configuration.clientAudioSource,
            sourceLabel = sourceLabel(configuration.clientAudioSource),
            deviceLabel = deviceLabel(configuration.audioDevice?.type),
            effects = effects,
            clientEffects = clientEffects,
        )
    }

    companion object {
        fun sourceLabel(source: Int): String = when (source) {
            MediaRecorder.AudioSource.UNPROCESSED -> "UNPROCESSED"
            MediaRecorder.AudioSource.VOICE_RECOGNITION -> "VOICE_RECOGNITION"
            MediaRecorder.AudioSource.MIC -> "MIC"
            MediaRecorder.AudioSource.CAMCORDER -> "CAMCORDER"
            MediaRecorder.AudioSource.VOICE_COMMUNICATION -> "VOICE_COMMUNICATION"
            else -> "source $source"
        }

        fun effectLabel(type: UUID): String = when (type) {
            AudioEffect.EFFECT_TYPE_AGC -> "AGC"
            AudioEffect.EFFECT_TYPE_NS -> "NS"
            AudioEffect.EFFECT_TYPE_AEC -> "AEC"
            else -> type.toString()
        }

        fun deviceLabel(type: Int?): String = when (type) {
            null -> "none"
            AudioDeviceInfo.TYPE_BUILTIN_MIC -> "BUILTIN_MIC"
            AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> "BLUETOOTH_SCO"
            AudioDeviceInfo.TYPE_WIRED_HEADSET -> "WIRED_HEADSET"
            AudioDeviceInfo.TYPE_USB_DEVICE -> "USB_DEVICE"
            // A USB-C microphone with a headphone jack on it — which is most of
            // them, including the VideoMic Me-C — enumerates as a *headset*
            // rather than a device, because it presents both an input and an
            // output. Unlabelled it read as "type 22" in the picker, exactly
            // when somebody is trying to confirm a new microphone works.
            AudioDeviceInfo.TYPE_USB_HEADSET -> "USB_HEADSET"
            AudioDeviceInfo.TYPE_USB_ACCESSORY -> "USB_ACCESSORY"
            AudioDeviceInfo.TYPE_BLUETOOTH_A2DP -> "BLUETOOTH_A2DP"
            // Virtual inputs a Pixel enumerates alongside the real ones. Not
            // offered as microphones — ECHO_REFERENCE is the phone's own
            // playback — but named here so a diagnostic dump is readable.
            AudioDeviceInfo.TYPE_REMOTE_SUBMIX -> "REMOTE_SUBMIX (virtual)"
            // TYPE_ECHO_REFERENCE is not public API, so the value rather than
            // the constant. A Pixel enumerates it among its inputs regardless.
            28 -> "ECHO_REFERENCE (virtual)"
            else -> "type $type"
        }
    }
}
