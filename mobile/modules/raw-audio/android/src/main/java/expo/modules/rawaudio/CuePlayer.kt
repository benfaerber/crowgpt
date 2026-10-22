package expo.modules.rawaudio

import android.content.Context
import android.content.res.AssetFileDescriptor
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.ToneGenerator
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

/**
 * Says [Cue]s out loud — through the earbuds when any are connected, through
 * the vibration motor when none are.
 *
 * ToneGenerator on STREAM_MUSIC rather than an audio asset: that is the stream
 * a Bluetooth headset is already on, there is no file to ship, and nothing can
 * stall decoding at the moment the button was pressed. The haptic path is the
 * degraded one and known to be — the phone rides in a crossbody bag, where a
 * vibration may not be felt at all.
 */
class CuePlayer(private val context: Context) {

    fun play(cue: Cue) {
        if (bluetoothOutputConnected()) beep(cue) else buzz(cue)
    }

    /**
     * A repeating cue, said over whatever else is playing.
     *
     * Two needs a one-off cue does not have. Audibility: the heartbeat's whole
     * job is to be heard over the podcast, so focus is taken as
     * TRANSIENT_MAY_DUCK for the length of the tone and the music dips rather
     * than pauses. And fade-out hygiene: playing while another app holds focus
     * is exactly how a uid lands in the audio server's faded set, where every
     * new player is born muted — [MediaButtonPriority.withBlipFocus] learned
     * that the hard way, and regaining focus is the only documented exit. A
     * heartbeat that plays hundreds of times a walk must clear the fade each
     * beat or its own first collision silences every beat after it.
     */
    fun playDucked(cue: Cue) {
        if (!bluetoothOutputConnected()) {
            buzz(cue)
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            beep(cue)
            return
        }
        val manager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            .build()
        runCatching { manager.requestAudioFocus(request) }
        beep(cue)
        Handler(Looper.getMainLooper()).postDelayed(
            { runCatching { manager.abandonAudioFocusRequest(request) } },
            cue.toneMs + 200L,
        )
    }

    /**
     * Play the bundled phrase, ducking whatever else is on the earbuds.
     *
     * Words rather than a tone only for the rare, exceptional cue — see
     * [SpokenCue] for why the heartbeat is not one. Returns null if the player
     * never starts, so the caller can fall back to a tone rather than leaving
     * the moment silent; the audio route is being torn down when this is
     * called, which is not the time to trust a MediaPlayer.
     *
     * An error AFTER start() used to be the gap: with only a completion
     * listener, a player that died mid-route-collapse was silence reported as
     * success — five AirPods pulls on 2026-08-01 logged "words" and delivered
     * nothing. The error listener now plays the failure tone itself, so the
     * worst outcome is a beep instead of a guess.
     *
     * Same focus dance as [playDucked], and for the same two reasons: audible
     * over a podcast, and clearing the fade this uid would otherwise be left
     * in. The grant is reported rather than assumed — a refused grant leaves
     * the fade in place, and a faded player "plays" to completion inaudibly.
     *
     * USAGE_MEDIA, NOT USAGE_ASSISTANCE_SONIFICATION. Sonification maps to
     * the system stream, which a phone set to vibrate mutes outright and
     * earbuds carry at system volume rather than the media volume the wearer
     * actually set — so the words were inaudible on exactly the phone that
     * goes to the field, while the tones played fine because ToneGenerator
     * names STREAM_MUSIC outright. The class doc's reason for that choice —
     * "the stream a Bluetooth headset is already on" — applies to the words
     * with more force than to the beeps.
     */
    fun speak(source: AssetFileDescriptor): Spoken? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return null
        val manager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val attributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(attributes)
            .build()
        val player = MediaPlayer()
        fun cleanup() {
            runCatching { player.release() }
            runCatching { manager.abandonAudioFocusRequest(request) }
        }
        return runCatching {
            player.setAudioAttributes(attributes)
            source.use { player.setDataSource(it.fileDescriptor, it.startOffset, it.length) }
            player.prepare()
            val granted = runCatching { manager.requestAudioFocus(request) }
                .getOrDefault(AudioManager.AUDIOFOCUS_REQUEST_FAILED) ==
                AudioManager.AUDIOFOCUS_REQUEST_GRANTED
            player.setOnCompletionListener { cleanup() }
            player.setOnErrorListener { _, _, _ ->
                cleanup()
                play(Cue.FAILED)
                true
            }
            player.start()
            Spoken(routeOf(player), granted)
        }.getOrElse {
            cleanup()
            null
        }
    }

    /** What [speak] managed once the player started. */
    data class Spoken(val route: String?, val focusGranted: Boolean)

    /**
     * Where the framework says a started player's audio is going — the answer
     * to "did this route into the USB device being unplugged, or the earbuds?"
     */
    private fun routeOf(player: MediaPlayer): String? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) return null
        return runCatching {
            player.routedDevice?.let { "${it.type}:${it.productName}" }
        }.getOrNull()
    }

    /** Shared with the armed indicator, which asks the same question. */
    fun bluetoothOutputConnected(): Boolean {
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        return am.getDevices(AudioManager.GET_DEVICES_OUTPUTS).any {
            it.type == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP
                || it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO
                || it.type == AudioDeviceInfo.TYPE_BLE_HEADSET
                || it.type == AudioDeviceInfo.TYPE_BLE_BROADCAST
                || it.type == AudioDeviceInfo.TYPE_HEARING_AID
        }
    }

    private fun beep(cue: Cue) {
        val tones = ToneGenerator(AudioManager.STREAM_MUSIC, VOLUME)
        tones.startTone(cue.tone, cue.toneMs)
        // startTone returns before the sound ends; releasing immediately cuts
        // it off mid-beep.
        Handler(Looper.getMainLooper()).postDelayed({ tones.release() }, cue.toneMs + 150L)
    }

    private fun buzz(cue: Cue) {
        val vibrator =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val manager =
                    context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
                manager.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createWaveform(cue.vibration, -1))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(cue.vibration, -1)
        }
    }

    private companion object {
        /**
         * Relative to the media volume the earbuds are already set to, not
         * absolute — 100 at a walking-around volume is a flinch, not a cue.
         */
        const val VOLUME = 80
    }
}
