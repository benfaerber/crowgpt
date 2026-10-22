package expo.modules.rawaudio

import android.content.Context

/**
 * The one phrase this app speaks, shipped as a recording.
 *
 * It used to be rendered on the handset by TextToSpeech, which meant an engine
 * that might not exist, voice data that might not be downloaded, a cache file
 * Android was free to clear, and a diagnostics probe to tell those silences
 * apart. A recording bundled at res/raw needs none of it: it cannot be missing,
 * cannot render as 44 bytes of header, and being PCM it needs no decoder at the
 * one moment this plays — while the audio route it is about to describe is
 * being torn down.
 *
 * The heartbeat stays tones on purpose — it fires hundreds of times a walk and
 * a spoken "recording" would land in the capture. This is the other kind of
 * cue: rare, exceptional, and useless if it is ambiguous.
 */
class SpokenCue(private val resource: Int) {

    /**
     * Say it, or make the nearest sound available, and report which it was.
     *
     * The fallback matters more than it looks: this fires when a microphone has
     * just gone, which is the one moment a person must not be left guessing. A
     * player that will not start still gets the error tone, and a phone with no
     * earbuds connected still gets the vibration [CuePlayer] already falls back
     * to — known to be weak in a crossbody bag, and still better than the
     * passer-by who was the alert last time.
     *
     * Everything [CuePlayer.speak] learned rides back on the result, because
     * WORDS alone proved to be a lie worth three field sessions: the AirPods
     * bug of 2026-08-01 logged cue="words" five times while delivering
     * silence. The route and the focus grant are what tell that story apart
     * next time without pulling a microphone to reproduce it.
     */
    fun announce(context: Context, requireEarbuds: Boolean = true): Announced {
        val player = CuePlayer(context)
        val toEarbuds = player.bluetoothOutputConnected()
        if (toEarbuds || !requireEarbuds) {
            val spoken = runCatching {
                context.resources.openRawResourceFd(resource)
            }.getOrNull()?.let { player.speak(it) }
            if (spoken != null) {
                return Announced(Said.WORDS, spoken.route, spoken.focusGranted)
            }
        }
        // Nothing to say it with, or nowhere anyone is listening. The tone is
        // still a tone through the phone's own speaker; only the words are held
        // back from it, because a phrase out loud lands in the recording.
        player.play(FALLBACK)
        return Announced(if (toEarbuds) Said.TONE else Said.BUZZ)
    }

    /** What [announce] managed, and what the audio system said while it did. */
    data class Announced(
        val said: Said,
        /** Where the started player was actually routed, when the OS will say. */
        val route: String? = null,
        /** Whether the focus request that clears a fade was granted. */
        val focusGranted: Boolean? = null,
    )

    enum class Said {
        /** The recording, through the earbuds — or at least a player claiming so. */
        WORDS,

        /** The failure tone, because the player would not start the phrase. */
        TONE,

        /** The vibration motor, because nothing is connected to hear words with. */
        BUZZ,
    }

    companion object {
        /** Alongside the tones in meaning: something is wrong and audio is affected. */
        val FALLBACK = Cue.FAILED

        val MIC_DISCONNECTED = SpokenCue(R.raw.mic_disconnected)
    }
}
