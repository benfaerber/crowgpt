package expo.modules.rawaudio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioPlaybackConfiguration
import android.media.AudioTrack
import android.os.Build
import android.os.Handler
import android.os.Looper

/**
 * Makes the MediaSession actually receive the button, not merely deserve it.
 *
 * Declaring STATE_PLAYING turned out to be theatre: MediaSessionService gives
 * the button to the session of the uid that most recently *played audio*, and
 * never reads the declared state. Measured on the Pixel 10 (dumpsys
 * media_session, 2026-07-29): our session active and PLAYING, and "Media
 * button session is com.google.android.youtube" — YouTube stopped, but heard
 * from more recently than an app that had never made a sound.
 *
 * So this makes the sound: a quarter second of silence on the media stream,
 * which is enough to top the recency list. And because recency is a contest,
 * it watches other apps' playback end and re-asserts — without that, one
 * YouTube video on the walk takes the button back for the rest of it.
 *
 * Focus is requested for the length of the blip and given straight back, which
 * reverses an earlier decision and is explained at [withBlipFocus]: it is not
 * for the focus, it is the only way out of a fade-out that would otherwise make
 * this app permanently invisible to the election. TRANSIENT_MAY_DUCK, so the
 * music the recordist is allowed to keep dips rather than pauses — the promise
 * is that this takes the button and never the audio.
 */
class MediaButtonPriority(private val context: Context) {
    private val handler = Handler(Looper.getMainLooper())
    private val decider = ReclaimDecider()
    private var blipsInFlight = 0
    private var watcher: AudioManager.AudioPlaybackCallback? = null
    private var held = false
    /**
     * Re-arms the MediaSession itself, alongside the recency blip.
     *
     * Recency decides who *receives* the button, but a session that has been
     * deactivated or whose playback state has gone stale can be skipped before
     * recency is even consulted. Losing the button is not one failure with one
     * cause, so re-claiming asserts both halves rather than guessing which one
     * went.
     */
    private var reassert: (() -> Unit)? = null

    private fun audioManager(): AudioManager =
        context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    fun claim(reassert: (() -> Unit)? = null) {
        this.reassert = reassert
        held = true
        contest()
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || watcher != null) return
        val callback = object : AudioManager.AudioPlaybackCallback() {
            override fun onPlaybackConfigChanged(configs: List<AudioPlaybackConfiguration>) {
                if (decider.onPlayersChanged(
                        configs.size, blipsInFlight, System.currentTimeMillis(),
                    )
                ) {
                    contest()
                }
            }
        }
        audioManager().registerAudioPlaybackCallback(callback, handler)
        watcher = callback
    }

    /** Re-enter the contest: re-arm the session, then top the recency list. */
    private fun contest() {
        runCatching { reassert?.invoke() }
        blip()
    }

    fun release() {
        held = false
        reassert = null
        val callback = watcher ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            audioManager().unregisterAudioPlaybackCallback(callback)
        }
        watcher = null
    }

    /**
     * Ask for focus for the length of a blip, then give it straight back.
     *
     * Not for the focus. It is the only way to clear a fade-out.
     *
     * When a uid loses audio focus while it has a player running, the audio
     * server records that uid in FadeOutManager and applies a muting volume
     * shaper to *every new player it starts from then on*. A muted player is not
     * "active", an inactive player never bumps the uid in
     * AudioPlayerStateMonitor, and no bump means the media button election never
     * re-runs. The app becomes permanently invisible to the thing it is trying
     * to win, and nothing it does to its own MediaSession can help — the
     * election reads playback, not session state.
     *
     * The only documented exit is regaining focus, which calls unfadeOutUid.
     * TRANSIENT_MAY_DUCK rather than TRANSIENT so music dips rather than pauses:
     * the promise this feature makes is that it takes the button and never the
     * audio, and a quarter second of duck is the smallest price that keeps it.
     */
    private fun withBlipFocus(play: () -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            play()
            return
        }
        val manager = audioManager()
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build(),
            )
            .build()
        runCatching { manager.requestAudioFocus(request) }
        play()
        handler.postDelayed({ runCatching { manager.abandonAudioFocusRequest(request) } }, BLIP_MS)
    }

    private fun blip() {
        // A blip at zero media volume is muted by the stream, which makes it
        // inactive, which makes it invisible to the election — the same dead end
        // as the fade, reached a different way. Nothing to be done about it, but
        // pretending it worked would be worse.
        if (audioManager().getStreamVolume(AudioManager.STREAM_MUSIC) == 0) return
        withBlipFocus { playSilence() }
    }

    private fun playSilence() {
        // Mono 8 kHz because nobody will hear it; the point is the uid
        // appearing in the playback history, not the audio.
        //
        // Silent SAMPLES at full track volume, never setVolume(0f): a track
        // muted by client volume is excluded from the playback monitor for the
        // same reason a faded one is, and would defeat the whole exercise.
        val buffer = ByteArray(SAMPLE_RATE / 2)
        val track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(SAMPLE_RATE)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(buffer.size)
            .build()
        track.write(buffer, 0, buffer.size)
        blipsInFlight += 1
        track.play()
        handler.postDelayed({
            track.release()
            blipsInFlight -= 1
        }, BLIP_MS)
    }

    private companion object {
        const val SAMPLE_RATE = 8000
        /** Longer than the buffer plays, so release never cuts a live track. */
        const val BLIP_MS = 400L
    }
}

/**
 * When the recency contest is worth re-entering. Pure, so the sequences live in
 * a JVM test.
 *
 * ONE MOMENT ONLY: when everything else has stopped. That was the original
 * rule, it was replaced with a more aggressive one on 2026-07-30, and the
 * aggressive one was wrong in a way worth recording so nobody reinstates it.
 *
 * It contested when others started and every ten seconds while they continued,
 * reasoning that recency is a contest and should be entered continuously. Both
 * additions were harmful:
 *
 *   - The election picks the most recently *active* player, so an app that is
 *     still playing is still the most recent. A blip mid-playback cannot win.
 *   - Worse, it could lose permanently. A uid holding a live player at the
 *     moment it loses audio focus is added to the audio server's faded set, and
 *     every player it starts afterwards is born muted — inactive, and therefore
 *     invisible to the election, which reads playback and not session state.
 *     Blipping while another app plays is exactly how to be holding a live
 *     player when that app takes focus.
 *
 * So the aggressive version made the failure it was written to fix both more
 * likely and permanent. Ben saw it: once YouTube played, the button never came
 * back until the app was foregrounded — and foregrounding routes the key
 * through the focused window rather than the session, so it was never evidence
 * the session had recovered.
 *
 * The loop this must not have: our own blip is itself a playback config change,
 * so "any change → blip" blips forever. Own tracks are counted out, an edge is
 * used rather than a level, and a cooldown bounds the rate even if both of
 * those are wrong about some device's callback behaviour.
 */
internal class ReclaimDecider(private val cooldownMs: Long = COOLDOWN_MS) {
    private var othersPlaying = false
    private var lastBlipAt: Long? = null

    /**
     * @param activePlayers everything the audio policy currently has playing.
     * @param ownBlips how many of those are ours.
     * @return true when the button is worth contesting right now.
     */
    fun onPlayersChanged(activePlayers: Int, ownBlips: Int, now: Long): Boolean {
        val others = activePlayers > ownBlips
        val stopped = !others && othersPlaying
        othersPlaying = others
        // The falling edge only. Contesting on the rising one is what left this
        // app holding a live player at the moment another took focus, which is
        // the condition that fades a uid out permanently.
        return if (stopped) allow(now) else false
    }

    private fun allow(now: Long): Boolean {
        val last = lastBlipAt
        if (last != null && now - last < cooldownMs) return false
        lastBlipAt = now
        return true
    }

    companion object {
        /** Floor between two blips, however many reasons to blip arrive. */
        const val COOLDOWN_MS = 2_000L
    }
}
