package expo.modules.rawaudio

import android.content.Context
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.SystemClock
import java.io.File
import kotlin.math.sqrt

/**
 * Records effect-free 16-bit PCM to a WAV file.
 *
 * The whole point for bioacoustics: avoid the AGC / noise-suppression / echo
 * cancellation that phones apply to speech, which mangles faint or structured
 * bird calls.
 *
 * Sources are tried in preference order and the first one that opens wins. The
 * capability property is *not* the gate: devices that decline to certify
 * UNPROCESSED (every Pixel we have) still hand it over when asked, and on those
 * phones it measures identical to VOICE_RECOGNITION in SNR and frequency
 * response while sitting ~17 dB lower — headroom that keeps a close, loud caw
 * off the clipping ceiling. VOICE_RECOGNITION remains the fallback, and it too
 * carries no AGC/NS.
 *
 * Which one ran is never assumed — every capture reads its own record path back
 * from the audio policy via [RecordPathInspector], so `unprocessed` in the
 * result is a measurement of the effects actually attached, not a capability
 * flag. See mobile/README.md for the on-device evidence.
 */
class WavRecorder(private val context: Context) {

    private var thread: Thread? = null
    /** The microphone is open and the read loop is running. */
    /**
     * Every lifecycle flag, and the rules that move them. See [SessionState] —
     * it lives apart from this class so the transitions can be driven from a
     * JVM test rather than only from a phone, which is where all four of this
     * recorder's bugs came from.
     */
    private val session = SessionState()

    private var preRoll: PreRoll? = null
    private var preRollSeconds = 0.0

    /** What the next file is named. See RecordingOptions.prefix. */
    private var filePrefix = OrphanCaptures.CAPTURE_PREFIX
    private var preRollUsedBytes = 0
    /** Guards the WAV and the ring: the capture thread writes to both. */
    private val lock = Object()
    private var outputFile: File? = null
    /** The open WAV while recording; null means reads go to the ring instead. */
    private var capture: WavFile? = null
    private var sampleRate = 48000
    private val channels = 1
    private val bitsPerSample = 16
    @Volatile private var totalPcmBytes = 0L

    /**
     * Why the capture thread stopped early, if it did.
     *
     * The loop used to simply carry on: a read that returns an error code
     * returns it *every* time, so a microphone revoked mid-recording, an audio
     * server restart or a preferred device unplugged left this spinning at full
     * speed writing nothing, with the app still showing a running timer. A
     * recording that is not happening must say so.
     */
    @Volatile private var failure: String? = null

    /**
     * Told when the capture thread dies — a revoked microphone, an audio server
     * restart, a full disk. By the time it runs, [SessionState.fail] has ended
     * the session, so a listener that immediately stops or reopens finds
     * nothing half-held. Without this, a session dying in a pocket was
     * discovered at the next stop(), which could be an hour and any number of
     * missed calls later; until then the phone claimed to be listening to a
     * microphone it no longer had.
     */
    @Volatile var onFailure: ((message: String, whileRecording: Boolean) -> Unit)? = null

    /**
     * Every read's PCM, on the capture thread, whether listening or recording.
     *
     * The idle trigger's whole feed: the level meter above is throttled and
     * broadband, and a trigger needs every buffer in its own band. A tap
     * rather than a feature of this class — the recorder stays a recorder,
     * and whoever installs this owns what it costs.
     */
    @Volatile var onPcm: ((buffer: ByteArray, read: Int) -> Unit)? = null

    /**
     * How long to wait for a capture thread to return from a read.
     *
     * Half a second of audio per read at 48 kHz, so three seconds is six reads
     * of headroom. It is a bound on how long a stop can block, not a promise
     * that the thread has gone — the session number is what makes it safe
     * either way.
     */
    private val JOIN_MS = 3000L
    @Volatile private var reading: RecordPathInspector.Reading? = null
    @Volatile private var routedDevice: String? = null
    /**
     * The routed device as a *preference* rather than a label, so the app can
     * compare it against what it asked for without parsing prose. Same value as
     * [routedDevice], read from the same place at the same moment.
     */
    @Volatile private var routedType: Int? = null
    /**
     * The route a session was on when it died on its own, and when that was.
     *
     * Survives the next session opening, which is the entire point: a
     * microphone being pulled out kills the session and the app then reopens on
     * the phone mic, so by the time anything asks "what was lost" the live
     * answer is the replacement. Deliberately not cleared — [MicDisconnect]
     * bounds how long it stays interesting, and clearing it here would put the
     * race straight back.
     */
    @Volatile private var failedRoute: MicRoute? = null
    private var requestedSource = SOURCE_PREFERENCE.first()
    private var requestedInput: String = AudioInputs.BUILT_IN
    /** Whether the policy accepted the pin. Null when none was asked for. */
    private var preferredHonoured: Boolean? = null

    /**
     * Whether the device *certifies* an unprocessed source. Per CDD 5.11 a device
     * that supports it must report "true" here and one that doesn't must report
     * null — so anything but "true" means no certification. This says nothing
     * about whether opening UNPROCESSED would succeed; it usually does anyway.
     */
    fun isUnprocessedSupported(): Boolean {
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        return am.getProperty(AudioManager.PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED) == "true"
    }

    fun isRecording(): Boolean = session.recording

    fun isListening(): Boolean = session.isListening()

    /** The open session's rate, for anything filtering its PCM. */
    fun sampleRateNow(): Int = sampleRate

    /**
     * The file being written, if any. Orphan recovery needs it: a live capture
     * has no database row yet, so nothing else can tell it apart from one
     * abandoned by a dead process.
     */
    fun currentPath(): String? = synchronized(lock) { outputFile?.absolutePath }

    /**
     * Which microphone the open session is actually on — the one fact the app
     * could not previously ask for.
     *
     * The screen used to answer this by re-resolving the preference list against
     * what is plugged in *now*, which is a prediction about the next recording
     * and not a statement about the open one. The two part company the moment a
     * microphone is plugged in after the buffer starts: this session stays on
     * whatever it pinned, because the device is chosen once in `openAndRun` and
     * `start` cannot change it, while the prediction happily switches. That gap
     * recorded capture 107 on the phone mic under a caption naming the Rode.
     *
     * `routed` is null until the policy has actually chosen, which is the first
     * read with data — a caller that finds it null should say "opening" rather
     * than guess.
     */
    fun activeInput(): Map<String, Any?>? {
        if (!session.active) return null
        return mapOf(
            "requested" to requestedInput,
            "routed" to routedType?.let { AudioInputs.preferenceFor(it) },
            "routedLabel" to routedDevice,
            "honoured" to preferredHonoured,
            "recording" to session.recording,
        )
    }

    /**
     * Every microphone in play, as `AudioDeviceInfo.getType()`s: the one the
     * open session is on, and the one a session died on under it.
     *
     * The same fact [activeInput] reports, minus the prose — the disconnect cue
     * has to compare it against the raw types Android hands to
     * `onAudioDevicesRemoved`, and re-parsing a preference string to do that
     * would put the `builtin`/`type:15` spelling trap back in play.
     *
     * Both, rather than only the live one, because unplugging the microphone is
     * a thing that happens *to* the session: the read fails, [SessionState.fail]
     * closes it, and the app swaps onto the phone mic. Asking which mic is open
     * at that moment returns either nothing or the replacement, and the answer
     * the cue needs is the one that just left. See [MicDisconnect].
     */
    fun routesInPlay(): List<MicRoute> = listOfNotNull(
        if (session.active) routedType?.let { MicRoute(it, endedAtMs = null) } else null,
        failedRoute,
    )

    /** First source in preference order that actually opens. */
    private fun open(
        sampleRate: Int,
        channelConfig: Int,
        encoding: Int,
        bufSize: Int,
    ): AudioRecord {
        for (source in SOURCE_PREFERENCE) {
            val record = try {
                AudioRecord(source, sampleRate, channelConfig, encoding, bufSize)
            } catch (e: IllegalArgumentException) {
                continue
            }
            if (record.state == AudioRecord.STATE_INITIALIZED) {
                requestedSource = source
                return record
            }
            record.release()
        }
        throw IllegalStateException("AudioRecord init failed — RECORD_AUDIO permission?")
    }

    /**
     * Open the microphone and keep the last `preRollSeconds` in memory without
     * writing anything to disk.
     *
     * The whole point of the pre-roll: by the time a call has been heard and the
     * button reached, it is over. Listening first means [start] can begin the
     * recording in the past.
     *
     * The meter runs while listening, so the level display works before anyone
     * has committed to a recording.
     */
    fun startListening(
        sampleRate: Int,
        input: String?,
        preRollSeconds: Double,
        onLevel: (Double) -> Unit,
    ) {
        session.beginListening()
        this.preRollSeconds = preRollSeconds
        synchronized(lock) {
            preRoll = PreRoll(PreRoll.sizeFor(preRollSeconds, sampleRate))
        }
        openAndRun(sampleRate, input, onLevel, writing = false)
    }

    /** Close the microphone and drop whatever the ring was holding. */
    fun stopListening() {
        session.endListening()
        awaitThread()
        synchronized(lock) {
            preRoll?.clear()
            preRoll = null
        }
    }

    /**
     * Tear everything down without erasing evidence. For the module's
     * OnDestroy, where nobody is coming back to call stop(): a reloaded JS
     * bundle gets a fresh recorder, and whatever this one held would otherwise
     * run on unfindable — the thread looping on a session nothing could ever
     * retire, holding the microphone until the process died.
     *
     * An open WAV is closed so its header is honest, but its writing marker
     * stays: the capture's row was never entered, and the marker is what lets
     * the next launch recover the file instead of reading it as deleted.
     */
    fun destroy() {
        onFailure = null
        onPcm = null
        session.retire()
        awaitThread()
        synchronized(lock) {
            runCatching { closeWav() }
            preRoll = null
        }
    }

    /**
     * Retire the current session and wait, briefly, for its thread.
     *
     * The wait is a courtesy rather than a guarantee: `AudioRecord.read` blocks
     * until it has audio or the record stops, so a thread can take a moment to
     * come back. Retiring the generation first is what makes the timeout safe —
     * whenever that thread wakes it finds itself out of date and leaves without
     * touching anything the next session owns.
     */
    private fun awaitThread() {
        thread?.join(JOIN_MS)
        thread = null
    }

    /**
     * Refuse to open a second microphone on top of a thread that has not gone.
     *
     * Two `AudioRecord`s in one process is a coin toss: the second may come back
     * uninitialised, or take the route the first was using. Neither reports
     * anything a person would recognise as the cause, so this stops with a
     * sentence instead — and only after giving the old thread a second chance,
     * because the usual reason it is still there is that it is mid-read.
     */
    private fun awaitPreviousThread() {
        val previous = thread ?: return
        if (!previous.isAlive) {
            thread = null
            return
        }
        previous.join(JOIN_MS)
        if (previous.isAlive) {
            throw IllegalStateException(
                "the previous capture thread is still running — the microphone " +
                    "was not released",
            )
        }
        thread = null
    }

    /**
     * Start capture; returns the output file path. `onLevel` gets a 0..1 RMS meter.
     *
     * `input` pins which microphone is used — by default the phone's own, so a
     * paired headset cannot quietly capture the corpus through a narrowband
     * speech path. See [AudioInputs].
     *
     * If already listening, the recording opens with the pre-roll — the seconds
     * before the button was pressed — and continues live from there.
     */
    fun start(
        sampleRate: Int,
        input: String?,
        onLevel: (Double) -> Unit,
        prefix: String = OrphanCaptures.CAPTURE_PREFIX,
    ): String {
        filePrefix = prefix
        if (session.beginRecording()) return beginCapture()

        this.preRollSeconds = 0.0
        return openAndRun(sampleRate, input, onLevel, writing = true)
            ?: error("capture did not start")
    }

    /**
     * Say on disk that this file is being written, so a process that dies now
     * can be told apart from a capture somebody deleted later. Cleared by
     * [closeCapture]. See OrphanCaptures.WRITING_MARKER.
     */
    private fun markWriting(file: File) {
        runCatching { OrphanCaptures.markerFor(file).createNewFile() }
    }

    /** Close the WAV, patching its lengths. The marker is the caller's call. */
    private fun closeWav() {
        capture?.close()
        capture = null
    }

    /**
     * Close the WAV and drop its marker, in that order — a marker removed
     * before the lengths are patched would leave an unrecoverable file if the
     * process died between the two.
     */
    private fun closeCapture() {
        closeWav()
        outputFile?.let { runCatching { OrphanCaptures.markerFor(it).delete() } }
    }

    /** Begin writing, seeded with whatever the ring holds. */
    private fun beginCapture(): String {
        val file = File.createTempFile(filePrefix, ".wav", context.cacheDir)
        markWriting(file)
        synchronized(lock) {
            val head = preRoll?.drain() ?: ByteArray(0)
            preRollUsedBytes = head.size
            val wav = WavFile(file, sampleRate, channels)
            wav.write(head, head.size)
            totalPcmBytes = head.size.toLong()
            capture = wav
            outputFile = file
        }
        return file.absolutePath
    }

    private fun openAndRun(
        sampleRate: Int,
        input: String?,
        onLevel: (Double) -> Unit,
        /** True when this session writes from its first byte — `start` with no
         *  microphone already open. False when it fills the ring instead. */
        writing: Boolean,
    ): String? {
        // Before anything is opened: one microphone at a time, and a clear
        // refusal rather than two.
        awaitPreviousThread()
        this.sampleRate = sampleRate

        reading = null
        routedDevice = null
        routedType = null
        // A fresh microphone is a clean sheet. This used to survive into the
        // next session, so a listen that died quietly branded the next healthy
        // capture with its failure — failed tone, "stopped early", all of it
        // borrowed from a session already over.
        failure = null
        requestedInput = input ?: AudioInputs.BUILT_IN

        val channelConfig = AudioFormat.CHANNEL_IN_MONO
        val encoding = AudioFormat.ENCODING_PCM_16BIT
        val minBuf = AudioRecord.getMinBufferSize(sampleRate, channelConfig, encoding)
        if (minBuf <= 0) throw IllegalStateException("unsupported sample rate $sampleRate")
        val bufSize = maxOf(minBuf, sampleRate) // ~0.5s of 16-bit mono

        val audioRecord = open(sampleRate, channelConfig, encoding, bufSize)

        // Must be set on the constructed AudioRecord and before startRecording;
        // the policy picks the route when capture begins. A refusal is recorded
        // rather than thrown — a capture through the wrong mic still beats no
        // capture at all, and `device` in the result says which one it was.
        val chosen = AudioInputs.choose(context, requestedInput)
        preferredHonoured = when {
            // "auto" asked for nothing, so there is nothing to honour or refuse.
            chosen.device == null -> null
            // The requested microphone was not attached. The capture still
            // happens, through whatever is there, and says so.
            !chosen.matched -> {
                audioRecord.setPreferredDevice(chosen.device)
                false
            }
            else -> audioRecord.setPreferredDevice(chosen.device)
        }

        // When listening, nothing is written until `start` — the loop below
        // parks each read in the ring instead, and `beginCapture` opens the file.
        var path: String? = null
        if (writing) {
            val file = File.createTempFile(filePrefix, ".wav", context.cacheDir)
            markWriting(file)
            outputFile = file
            totalPcmBytes = 0
            preRollUsedBytes = 0
            synchronized(lock) {
                capture = WavFile(file, sampleRate, channels)
            }
            path = file.absolutePath
        }

        val myGeneration = session.open(writing)
        val inspector = RecordPathInspector(context)
        thread = Thread {
            audioRecord.startRecording()
            val buffer = ByteArray(bufSize)
            var sinceLevel = 0
            // Why this thread stopped early, if it did. Local as well as the
            // field: the field can be read and cleared by stop() while the
            // finally below still needs to know what happened here.
            var died: String? = null
            try {
                while (session.owns(myGeneration) && session.active) {
                    val read = audioRecord.read(buffer, 0, buffer.size)
                    if (read < 0) {
                        // Negative is an error code, and it is a *sticky* one:
                        // ERROR_DEAD_OBJECT, ERROR_INVALID_OPERATION and the
                        // rest come back on every subsequent call. Carrying on
                        // meant spinning a core in somebody's pocket while the
                        // file stopped growing.
                        died = "microphone read failed ($read)"
                        failure = died
                        break
                    }
                    if (read > 0) {
                        try {
                            synchronized(lock) {
                                // Re-checked while holding the lock: without it
                                // a thread could pass the loop condition, wait
                                // on the lock while a new session swapped the
                                // file underneath, and then write into it.
                                if (!session.owns(myGeneration)) return@synchronized
                                val wav = capture
                                // One branch, so a read is either recorded or
                                // held — never both, never dropped between.
                                if (wav != null) {
                                    wav.write(buffer, read)
                                    totalPcmBytes += read
                                } else {
                                    preRoll?.write(buffer, read)
                                }
                            }
                        } catch (error: Throwable) {
                            // Storage full, most likely. Stop rather than throw
                            // out of the thread: an exception here used to kill
                            // the loop while leaving `recording` true, so the
                            // screen showed a capture still running and `stop`
                            // handed back a truncated file as though it were
                            // whole.
                            died = "could not write audio: ${error.message ?: error}"
                            failure = died
                            break
                        }
                        sinceLevel += read
                        if (reading == null) {
                            reading = inspector.inspect(audioRecord.audioSessionId)
                            // Only meaningful once capture is live: before that
                            // the policy has not chosen a route yet.
                            routedType = audioRecord.routedDevice?.type
                            routedDevice = RecordPathInspector.deviceLabel(routedType)
                        }
                        if (sinceLevel >= sampleRate) { // ~2x/sec, don't flood the bridge
                            sinceLevel = 0
                            onLevel(rms16(buffer, read))
                        }
                        onPcm?.invoke(buffer, read)
                    }
                }
            } finally {
                audioRecord.stop()
                audioRecord.release()
                if (died != null) {
                    // The microphone is gone, so the session is over — said
                    // now, not left for the next stop() to trip over. The only
                    // exit that still owns its session is this one: every
                    // deliberate stop retires the generation first.
                    val wasRecording = session.recording
                    val owned = session.fail(myGeneration)
                    if (owned) {
                        // Which microphone went down with it, kept where the
                        // disconnect cue can still find it once this session is
                        // closed and the next one has opened on the phone mic.
                        failedRoute = routedType?.let {
                            MicRoute(it, endedAtMs = SystemClock.uptimeMillis())
                        }
                        synchronized(lock) {
                            // Close the WAV so its header is honest, but keep
                            // the writing marker: no capture row exists until
                            // stop() returns, and a process that dies before
                            // then must leave something recovery can find.
                            runCatching { closeWav() }
                        }
                        onFailure?.invoke(died, wasRecording)
                    }
                } else {
                    synchronized(lock) {
                        // Only this session's file. A stale thread closing the
                        // current capture would truncate a recording somebody
                        // is still making.
                        if (session.owns(myGeneration)) {
                            closeCapture()
                        }
                    }
                }
            }
        }.also { it.start() }

        return path
    }

    /**
     * Stop and return {path, durationMs, sampleRate, bytes, source, effects,
     * unprocessed, certifiedUnprocessed}.
     *
     * `unprocessed` is the measured answer — no capture effects were attached to
     * the record path. It is null when the path could not be read back.
     */
    fun stop(): Map<String, Any?> {
        val stillListening = session.endRecording()
        // Whatever the thread died of, the caller is told — and it is cleared
        // here so the next recording starts with a clean sheet.
        val died = failure
        failure = null

        if (stillListening) {
            // Close the file but leave the microphone open, so the ring is
            // already refilling. Crows call in bouts, and the second one is
            // missed just as easily as the first.
            synchronized(lock) {
                closeCapture()
            }
        } else {
            session.retire()
            awaitThread()
        }
        // The thread's finally block closes the file for a session that ended
        // with it, but only if it owned the session — and it may still be
        // inside a read. Idempotent, so saying it twice costs nothing and a
        // marker left behind by either path is a capture wrongly recovered.
        synchronized(lock) { closeCapture() }

        val file = outputFile ?: throw IllegalStateException("no output file")
        val frameBytes = channels * bitsPerSample / 8
        val durationMs = (totalPcmBytes / frameBytes.toDouble() / sampleRate * 1000).toLong()
        val path = reading
        return mapOf(
            "path" to file.absolutePath,
            // Null on a healthy capture. Set means the audio stops early and
            // the duration above describes what was written, not how long the
            // button was held.
            "failure" to died,
            "durationMs" to durationMs,
            "sampleRate" to sampleRate,
            "bytes" to file.length(),
            "source" to (path?.sourceLabel ?: RecordPathInspector.sourceLabel(requestedSource)),
            "sourceConfirmed" to (path != null),
            "device" to (path?.deviceLabel ?: routedDevice),
            "requestedInput" to requestedInput,
            // How much of this recording happened before the button was pressed.
            // Worth reporting rather than hiding: it is the difference between a
            // capture that starts on the call and one that starts after it.
            "preRollSec" to (preRollUsedBytes / (channels * bitsPerSample / 8).toDouble()
                / sampleRate),
            // The measured answer to "did the pin work?". A capture that went
            // through a headset anyway must be visible, not inferred later from
            // a recording that sounds wrong.
            "inputHonoured" to preferredHonoured,
            "effects" to (path?.effects ?: emptyList<String>()),
            "unprocessed" to path?.unprocessed,
            "certifiedUnprocessed" to isUnprocessedSupported(),
        )
    }

    private fun rms16(bytes: ByteArray, len: Int): Double {
        var sum = 0.0
        var i = 0
        while (i + 1 < len) {
            val s = (bytes[i].toInt() and 0xff) or (bytes[i + 1].toInt() shl 8)
            sum += (s.toShort().toDouble()) * s.toShort().toDouble()
            i += 2
        }
        val n = (len / 2).coerceAtLeast(1)
        return (sqrt(sum / n) / Short.MAX_VALUE).coerceIn(0.0, 1.0)
    }

    companion object {
        private val SOURCE_PREFERENCE = listOf(
            MediaRecorder.AudioSource.UNPROCESSED,
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
        )
    }
}
