package expo.modules.rawaudio

import android.content.Context
import android.content.Intent
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.MediaMetadata
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.KeyEvent
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * JS-facing surface of the raw-audio native module.
 *
 *   import RawAudio from "raw-audio";
 *   const supported = RawAudio.isUnprocessedSupported();
 *   const path = await RawAudio.startRecording({ sampleRate: 48000 });
 *   RawAudio.addListener("onAudioLevel", ({ level }) => setMeter(level));
 *   const info = await RawAudio.stopRecording(); // {path,durationMs,sampleRate,bytes,unprocessed}
 *
 * The app must hold RECORD_AUDIO (request it from JS, e.g. expo permissions)
 * before startRecording.
 */

class RawAudioModule : Module() {
    private var recorder: WavRecorder? = null

    /** The pocket-listening wish, reasserted after every session (re)open. */
    private val backgroundHold = BackgroundHold(
        listening = { recorder?.isListening() == true },
        serviceRunning = { ListeningService.running },
        startService = { appContext.reactContext?.let { ListeningService.start(it) } },
        stopService = { appContext.reactContext?.let { ListeningService.stop(it) } },
    )
    private var inputWatcher: AudioDeviceCallback? = null
    private var mediaSession: MediaSession? = null
    private var buttonPriority: MediaButtonPriority? = null

    /**
     * Claim the headset play/pause button.
     *
     * The button belongs to whichever app holds the active MediaSession, and
     * holding one is zero-sum: while this exists, YouTube's tap does nothing.
     * That is why it is acquired and released by explicit calls the setting
     * drives, not by observer hooks — released has to mean "YouTube has the
     * button back", with no listener lifecycle in between to reason about.
     *
     * The state is declared PLAYING although nothing plays — and that alone
     * proved to be theatre: the button actually follows which uid most
     * recently played audio, which is [MediaButtonPriority]'s whole job.
     *
     * A backgrounded session can still be reaped with the process. The
     * foreground service pocket listening starts is what keeps the process
     * alive, so the trigger is only dependable in a bag with listening on —
     * without it, a dead session looks exactly like this code not working.
     */
    /** Shared by both delivery paths, because the duplicate is between them. */
    private val pressGate = PressGate()

    private fun transportPress() {
        if (pressGate.accept(SystemClock.uptimeMillis())) {
            sendEvent("onMediaButton", mapOf<String, Any>())
        }
    }

    /**
     * A volume-shutter press, from the Activity key path — see
     * [RawAudioPackage]. Emitted as onMediaButton so JS has exactly one
     * trigger path and capture rows are made in exactly one place, the same
     * reasoning that shaped onIdle. Through the shared gate: a remote that
     * ever sends both volume keys for one press would otherwise start and
     * instantly stop.
     */
    private fun shutterPress(keyCode: Int) {
        if (pressGate.accept(SystemClock.uptimeMillis())) {
            sendEvent("onMediaButton", mapOf("keyCode" to keyCode))
        }
    }

    private fun acquireMediaButton() {
        // Already holding one: re-enter the contest rather than returning.
        //
        // This used to be a bare early return, which quietly made "take the
        // button again on every trip in and out of the app" do nothing at all —
        // the session existed, so the call became a no-op, and the one moment
        // most likely to have lost the button was the one moment nothing was
        // asserted. Re-arming is cheap and `claim` is written to be repeatable.
        mediaSession?.let { existing ->
            armSession(existing)
            buttonPriority?.claim { mediaSession?.let(::armSession) }
            return
        }
        val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
        val session = MediaSession(ctx, "cawtalker-headset-trigger")
        session.setCallback(
            object : MediaSession.Callback() {
                override fun onMediaButtonEvent(mediaButtonIntent: Intent): Boolean {
                    val key = keyEventFrom(mediaButtonIntent)
                        ?: return super.onMediaButtonEvent(mediaButtonIntent)
                    if (HeadsetButton.isToggle(key.keyCode, key.action, key.repeatCount)
                        && pressGate.accept(SystemClock.uptimeMillis())
                    ) {
                        sendEvent("onMediaButton", mapOf("keyCode" to key.keyCode))
                    }
                    // Swallow the UPs and repeats of our keys too, or the
                    // default handling turns them into a second onPlay.
                    if (HeadsetButton.claims(key.keyCode)) return true
                    return super.onMediaButtonEvent(mediaButtonIntent)
                }

                // An assistant saying "pause" arrives as a transport control,
                // never as a KeyEvent. Same button, same meaning — and some
                // stacks send this *as well as* the key for one tap, which is
                // what the gate is for.
                override fun onPlay() = transportPress()
                override fun onPause() = transportPress()
            },
            Handler(Looper.getMainLooper()),
        )
        // Some stacks skip a session with no metadata when deciding who gets the
        // button. Costs nothing to carry, and it is also what a phone shows on
        // the lock screen if it ever decides to show us.
        session.setMetadata(
            MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, "CrowGPT")
                .putString(MediaMetadata.METADATA_KEY_ARTIST, "Recording trigger")
                .build(),
        )
        armSession(session)
        mediaSession = session
        val priority = buttonPriority ?: MediaButtonPriority(ctx).also { buttonPriority = it }
        // Re-arming on every contest, not only here: a session can be
        // deactivated or go stale under us, and that is skipped before recency
        // is even consulted. Losing the button has more than one cause.
        priority.claim { mediaSession?.let(::armSession) }
    }

    /**
     * Declare the session active and playing, with a fresh position stamp.
     *
     * Re-applied rather than set once. The position timestamp in a PlaybackState
     * is part of how recent a session looks, and one built at claim time keeps
     * saying the same thing an hour into a walk.
     */
    private fun armSession(session: MediaSession) {
        session.setPlaybackState(
            PlaybackState.Builder()
                .setActions(
                    PlaybackState.ACTION_PLAY_PAUSE
                        or PlaybackState.ACTION_PLAY
                        or PlaybackState.ACTION_PAUSE
                        or PlaybackState.ACTION_STOP,
                )
                .setState(PlaybackState.STATE_PLAYING, 0, 1f, SystemClock.elapsedRealtime())
                .build(),
        )
        session.isActive = true
    }

    private fun releaseMediaButton() {
        buttonPriority?.release()
        buttonPriority = null
        mediaSession?.run {
            isActive = false
            release()
        }
        mediaSession = null
    }

    private fun keyEventFrom(intent: Intent): KeyEvent? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT, KeyEvent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT)
        }

    /** Decides which removals are worth a word; see [MicDisconnect]. */
    private val micDisconnect = MicDisconnect()

    /**
     * Say "microphone disconnected" when the session's own mic is what left,
     * and describe the decision either way.
     *
     * On the audio device callback's thread, so it must not throw and must not
     * block — the words are a bundled recording, and playback is handed to a
     * MediaPlayer that completes on its own.
     *
     * The returned map goes onto the `onInputsChanged` event and from there into
     * the app log, because the first version of this shipped, stayed silent in
     * the field, and left nothing at all to say whether the removal never
     * matched, the phrase was never rendered, or the words played to an earbud
     * that had already gone. Every one of those is one line here — and since
     * the AirPods bug logged "words" against silence five times, the line also
     * carries where the player was routed and whether the focus grant that
     * clears a fade was actually granted.
     */
    private fun describeRemoval(removed: Array<out AudioDeviceInfo>?): Map<String, Any?> {
        val types = removed?.map { it.type } ?: emptyList()
        val routes = recorder?.routesInPlay() ?: emptyList()
        val announce = micDisconnect.shouldAnnounce(types, routes, SystemClock.uptimeMillis())
        val announced = if (announce) {
            appContext.reactContext?.let { SpokenCue.MIC_DISCONNECTED.announce(it) }
        } else {
            null
        }
        return mapOf(
            "reason" to "removed",
            "removedTypes" to types,
            "routedTypes" to routes.map { it.type },
            "routeLive" to routes.any { it.endedAtMs == null },
            "said" to announced?.said?.name?.lowercase(),
            "cueRoute" to announced?.route,
            "cueFocus" to announced?.focusGranted,
        )
    }

    /** Tell JS whenever the set of inputs changes, so a cached list cannot go stale. */
    private fun watchInputs() {
        val ctx = appContext.reactContext ?: return
        if (inputWatcher != null) return
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val callback = object : AudioDeviceCallback() {
            override fun onAudioDevicesAdded(added: Array<out AudioDeviceInfo>?) {
                sendEvent("onInputsChanged", mapOf("reason" to "added"))
            }

            override fun onAudioDevicesRemoved(removed: Array<out AudioDeviceInfo>?) {
                // Decided before the event rather than after it: the event wakes
                // JS, which reopens the session on whatever is left, and the
                // route this has to look at is the one that just went.
                val detail = runCatching { describeRemoval(removed) }
                    .getOrElse { mapOf("reason" to "removed") }
                sendEvent("onInputsChanged", detail)
            }
        }
        // Null handler means the main looper, which is where the module's other
        // callbacks already run.
        am.registerAudioDeviceCallback(callback, null)
        inputWatcher = callback
    }

    private fun stopWatchingInputs() {
        val ctx = appContext.reactContext ?: return
        val watcher = inputWatcher ?: return
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        am.unregisterAudioDeviceCallback(watcher)
        inputWatcher = null
    }

    /**
     * The repeating state cues — a tick while listening, a double beep while
     * recording, silence while idle. Two timers because the two run at
     * different cadences on purpose; see [Heartbeat] for the mapping.
     *
     * Scheduled natively rather than from JS because the state matters most
     * from a pocket, where React Native's timers stop with the paused
     * activity. Each tick reads the recorder at its firing, so nothing needs
     * re-arming when a session opens or a recording begins.
     */
    private val heartbeatHandler = Handler(Looper.getMainLooper())

    /**
     * The live ticks, compared by identity inside their runnables — the same
     * generation idiom as SessionState. removeCallbacks alone loses the race
     * where a tick is already running: it would re-post itself after the
     * cancellation, and the beeping would survive the setting that stopped it.
     */
    @Volatile
    private var listeningBeat: Runnable? = null

    @Volatile
    private var recordingBeat: Runnable? = null

    private fun stopHeartbeats() {
        listeningBeat?.let { heartbeatHandler.removeCallbacks(it) }
        listeningBeat = null
        recordingBeat?.let { heartbeatHandler.removeCallbacks(it) }
        recordingBeat = null
    }

    private fun scheduleBeat(
        intervalMs: Long,
        stillMine: (Runnable) -> Boolean,
        cue: () -> Cue?,
    ): Runnable {
        val tick = object : Runnable {
            override fun run() {
                if (!stillMine(this)) return
                cue()?.let { c ->
                    appContext.reactContext?.let { CuePlayer(it).playDucked(c) }
                }
                heartbeatHandler.postDelayed(this, intervalMs)
            }
        }
        heartbeatHandler.postDelayed(tick, intervalMs)
        return tick
    }

    private fun startHeartbeats(listeningMs: Long, recordingMs: Long) {
        stopHeartbeats()
        if (listeningMs > 0) {
            listeningBeat = scheduleBeat(listeningMs, { listeningBeat === it }) {
                Heartbeat.listeningTick(
                    recording = recorder?.isRecording() == true,
                    listening = recorder?.isListening() == true,
                )
            }
        }
        if (recordingMs > 0) {
            recordingBeat = scheduleBeat(recordingMs, { recordingBeat === it }) {
                Heartbeat.recordingTick(recorder?.isRecording() == true)
            }
        }
    }

    /**
     * The armed idle session, if any. One at a time: arming replaces
     * nothing — the UI disarms first — and a retired runner's already-posted
     * commands are dropped by the identity check in [handleIdleCommand].
     */
    @Volatile
    private var idle: IdleRunner? = null
    private var idleUntilLabel = ""
    private var idleStopListeningOnDisarm = false

    private fun idleReason(reason: IdleTrigger.DisarmReason): String = when (reason) {
        IdleTrigger.DisarmReason.EXPIRED -> "expired"
        IdleTrigger.DisarmReason.CAPTURE_CAP -> "captureCap"
        IdleTrigger.DisarmReason.SESSION_FAILED -> "sessionFailed"
        IdleTrigger.DisarmReason.MANUAL -> "manual"
    }

    private fun idlePhase(phase: IdleTrigger.Phase): String = when (phase) {
        IdleTrigger.Phase.ARMED -> "armed"
        IdleTrigger.Phase.TRIGGERED -> "triggered"
        IdleTrigger.Phase.RECORDING -> "recording"
        IdleTrigger.Phase.STOPPING -> "stopping"
        IdleTrigger.Phase.COOLDOWN -> "cooldown"
        IdleTrigger.Phase.SUSPENDED -> "suspended"
        IdleTrigger.Phase.DISARMED -> "disarmed"
    }

    /** On the main looper, via the runner's dispatch. */
    private fun handleIdleCommand(runner: IdleRunner, command: IdleTrigger.Command) {
        if (idle !== runner) return
        when (command) {
            is IdleTrigger.Command.EmitStart ->
                sendEvent("onIdle", mapOf("action" to "start"))
            is IdleTrigger.Command.EmitStop ->
                sendEvent("onIdle", mapOf("action" to "stop"))
            is IdleTrigger.Command.Notify -> {
                val ctx = appContext.reactContext ?: return
                when (command.state) {
                    IdleTrigger.NotifyState.ARMED -> ListeningService.update(
                        ctx,
                        "Idle mode armed$idleUntilLabel",
                        "Recording starts when a crow calls. " +
                            "${runner.capturesMade} auto capture(s) so far.",
                    )
                    IdleTrigger.NotifyState.RECORDING -> ListeningService.update(
                        ctx, "Recording — auto-triggered", "A call tripped the idle trigger.",
                    )
                    IdleTrigger.NotifyState.REVERTED -> ListeningService.update(
                        ctx, ListeningService.DEFAULT_TITLE, ListeningService.DEFAULT_TEXT,
                    )
                }
            }
            is IdleTrigger.Command.Disarmed -> {
                idle = null
                runner.destroy()
                recorder?.onPcm = null
                sendEvent(
                    "onIdle",
                    mapOf(
                        "action" to "disarmed",
                        "reason" to idleReason(command.reason),
                        "capturesMade" to runner.capturesMade,
                    ),
                )
                // Done natively rather than left to JS, which may be asleep:
                // an armed hour that quietly became an armed night is the
                // microphone held with nobody meaning it.
                if (idleStopListeningOnDisarm) {
                    ListeningService.onStopRequested = null
                    recorder?.stopListening()
                    appContext.reactContext?.let { ListeningService.stop(it) }
                }
            }
        }
    }

    private fun recorder(): WavRecorder {
        val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
        return recorder ?: WavRecorder(ctx).also { fresh ->
            fresh.onFailure = { message, whileRecording ->
                // The trigger has nothing left to listen through. Said before
                // the event goes to JS, so the disarm rides the same queue.
                idle?.sessionFailed()
                if (!whileRecording) {
                    // Nothing is holding the microphone any more. A foreground
                    // notification saying "Microphone is open" over a closed
                    // one is the pocket lie this event exists to end — and it
                    // must not depend on JS being awake to hear the event.
                    appContext.reactContext?.let { ListeningService.stop(it) }
                }
                sendEvent(
                    "onSessionFailure",
                    mapOf("message" to message, "whileRecording" to whileRecording),
                )
            }
            recorder = fresh
        }
    }

    override fun definition() = ModuleDefinition {
        Name("RawAudio")

        // onInputsChanged fires when a microphone is plugged in or pulled out.
        //
        // Without it the cached input list only refreshed when Settings opened
        // or a recording started, so plugging the USB mic in while looking at
        // the record screen left "… isn't connected" on screen indefinitely and
        // nothing said otherwise. Polling was the alternative: AudioManager's
        // device list was moved off the JS thread for being slow, so asking it
        // repeatedly is the thing that move was avoiding.
        // onMediaButton fires on a headset play/pause tap while the trigger
        // setting holds a MediaSession — see acquireMediaButton.
        // onSessionFailure fires when the open microphone session dies on its
        // own — revoked mic, dead audio server, full disk. The session is
        // already over when it arrives; a recording's remains are collected
        // with stopRecording as usual. Without it, a session dying in a pocket
        // was discovered at the next stop, hours and missed calls later.
        // onIdle carries the trigger's requests while idle mode is armed:
        // "start" and "stop" ask JS to drive the normal record path (the same
        // shape as onMediaButton, so capture rows are made in exactly one
        // place), and "disarmed" says the session ended and why.
        Events("onAudioLevel", "onInputsChanged", "onMediaButton", "onSessionFailure", "onIdle")

        OnStartObserving("onInputsChanged") {
            watchInputs()
        }

        OnStopObserving("onInputsChanged") {
            stopWatchingInputs()
        }

        Function("isUnprocessedSupported") {
            recorder().isUnprocessedSupported()
        }

        Function("isRecording") {
            recorder?.isRecording() ?: false
        }

        Function("isListening") {
            recorder?.isListening() ?: false
        }

        /**
         * What the open session is pinned to, or null when nothing is open.
         *
         * Synchronous because it only reads fields the capture thread has
         * already published — no trip to the audio HAL, unlike `listInputs`.
         * The UI renders from this, so an async answer would mean a frame
         * showing the old microphone.
         */
        Function("activeInput") {
            recorder?.activeInput()
        }

        /**
         * Whether some other app is putting audio out right now.
         *
         * The single variable that decides whether the headset button works:
         * the button goes to whoever played most recently, so an app that is
         * still playing is an app still winning. Exposed for the diagnostics
         * screen, because "it worked with YouTube and not with Spotify" took a
         * field session to notice and is one line to display.
         */
        Function("isOtherAudioPlaying") {
            val manager = appContext.reactContext
                ?.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            manager?.isMusicActive ?: false
        }

        /**
         * Open the mic and hold the last few seconds without writing anything.
         *
         * By the time a call has been heard and the button reached, it is over.
         * Listening first is what lets `startRecording` begin in the past.
         */
        AsyncFunction("startListening") { options: ListeningOptions?, promise: Promise ->
            try {
                val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
                val opts = options ?: ListeningOptions()
                // Only when asked to survive the screen going off. Android
                // denies a backgrounded app the microphone without a
                // microphone-type foreground service, so this has to be running
                // *before* the mic opens — which is why this is a direct start
                // rather than a `reassert`, whose listening check would refuse
                // it. Starting it for a session that only needs to last while
                // somebody is looking at the screen would put a permanent
                // notification on the phone for nothing.
                backgroundHold.expect(opts.background)
                if (opts.background) ListeningService.start(ctx)
                // How the service lets go of the microphone when the app is
                // swiped out of recents. Installed for the life of the session
                // and cleared when it ends.
                ListeningService.onStopRequested = { recorder?.stopListening() }
                recorder().startListening(opts.sampleRate, opts.input, opts.preRollSeconds) {
                    sendEvent("onAudioLevel", mapOf("level" to it))
                }
                promise.resolve(null)
            } catch (e: Exception) {
                // Leaving the service up would hold a notification claiming the
                // microphone is open when it is not.
                appContext.reactContext?.let { ListeningService.stop(it) }
                promise.reject("ERR_LISTEN_START", e.message, e)
            }
        }

        /**
         * Turn pocket listening on or off without closing the microphone.
         *
         * The service holds the *permission*, not the audio, so this can change
         * under a live session. It has to be its own call: the setting used to
         * be read only when listening started, so switching it off left the
         * service — and its notification, and the background microphone —
         * running until something else happened to stop them.
         */
        AsyncFunction("setBackground") { enabled: Boolean, promise: Promise ->
            try {
                if (appContext.reactContext == null) throw Exceptions.ReactContextLost()
                // The wish is remembered even when it cannot be granted yet: a
                // request landing while the session is between a stop and a
                // start used to be told no, once, forever — pocket listening
                // then believed it was on while nothing held the process. Now
                // the next session (re)open reasserts it. The resolved value
                // still says what is true at this moment, because "switch on,
                // nothing happens" being invisible is how this was lost for an
                // afternoon.
                promise.resolve(backgroundHold.set(enabled))
            } catch (e: Exception) {
                promise.reject("ERR_LISTEN_BACKGROUND", e.message, e)
            }
        }

        /**
         * Reopen the rolling buffer on a different microphone without ending
         * pocket listening.
         *
         * The route change that prompts a swap — earbuds arriving as another
         * app resumes on them — happens in the background as often as not,
         * and a backgrounded stop/start pair loses the foreground service
         * permanently. See [MicrophoneSwap] for the rule this enforces.
         *
         * `options.background` is ignored: whether the service runs is decided
         * by `startListening` and `setBackground`, and a swap preserves it.
         * `ListeningService.onStopRequested` stays installed for the same
         * reason — the session it lets go of is the one being reopened.
         */
        AsyncFunction("swapListening") { options: ListeningOptions?, promise: Promise ->
            try {
                val opts = options ?: ListeningOptions()
                MicrophoneSwap(
                    listening = { recorder?.isListening() == true },
                    closeSession = { recorder?.stopListening() },
                    openSession = {
                        recorder().startListening(
                            opts.sampleRate, opts.input, opts.preRollSeconds,
                        ) {
                            sendEvent("onAudioLevel", mapOf("level" to it))
                        }
                    },
                    standDownService = {
                        // Mirrors stopListening: nothing holds the microphone
                        // now, so neither the notification nor the swipe-away
                        // callback may outlive it.
                        ListeningService.onStopRequested = null
                        appContext.reactContext?.let { ListeningService.stop(it) }
                    },
                ).swap()
                // The session is open again — the moment a refused wish can be
                // granted. A `setBackground` that landed mid-swap was answered
                // from a closed session and gave up; without this the process
                // stays reapable while the setting says pocket listening is on.
                backgroundHold.reassert()
                promise.resolve(null)
            } catch (e: Exception) {
                promise.reject("ERR_LISTEN_SWAP", e.message, e)
            }
        }

        /**
         * Arm or disarm the idle trigger. Null disarms; an auto capture in
         * flight is ended and filed first.
         *
         * Refuses to arm without an open buffer: the trigger reads the
         * listening session's PCM, and arming a closed microphone would be a
         * session that can never fire — the silent failure worse than the
         * refusal. JS opens listening (with the service) before calling this.
         */
        AsyncFunction("setIdle") { options: IdleOptions?, promise: Promise ->
            try {
                if (options == null) {
                    idle?.disarm()
                    promise.resolve(null)
                    return@AsyncFunction
                }
                val rec = recorder()
                if (!rec.isListening()) {
                    throw IllegalStateException(
                        "idle mode needs the rolling buffer open before arming",
                    )
                }
                check(idle == null) { "idle mode is already armed" }
                idleStopListeningOnDisarm = options.stopListeningOnDisarm
                idleUntilLabel =
                    if (options.untilLabel.isBlank()) "" else " ${options.untilLabel}"
                var runner: IdleRunner? = null
                runner = IdleRunner(
                    IdleTrigger.Config(
                        armSeconds = options.armSeconds,
                        holdSeconds = options.holdSeconds,
                        maxCaptureSeconds = options.maxCaptureSeconds,
                        maxCaptures = options.maxCaptures,
                        triggerDb = options.triggerDb,
                        minDb = options.minDb,
                    ),
                    rec.sampleRateNow(),
                ) { command -> runner?.let { handleIdleCommand(it, command) } }
                idle = runner
                // Reads the field on every buffer, so disarming tears the tap
                // out without touching the recorder again.
                rec.onPcm = { buffer, read -> idle?.onPcm(buffer, read) }
                appContext.reactContext?.let {
                    ListeningService.update(
                        it,
                        "Idle mode armed$idleUntilLabel",
                        "Recording starts when a crow calls. Nothing else is saved.",
                    )
                }
                promise.resolve(null)
            } catch (e: Exception) {
                promise.reject("ERR_IDLE", e.message, e)
            }
        }

        /**
         * What the armed session is doing, for the UI to re-sync from after a
         * trip through the background. Null when nothing is armed.
         */
        Function("idleState") {
            val runner = idle ?: return@Function null
            mapOf(
                "phase" to idlePhase(runner.phase),
                "remainingMs" to runner.remainingMs(),
                "capturesMade" to runner.capturesMade,
                // The live meter: what the trigger hears, what it calls
                // quiet, and the line it fires over. The screen polls this
                // once a second while armed.
                "bandDb" to runner.lastBandDb,
                "floorDb" to runner.lastFloorDb,
                "thresholdDb" to runner.thresholdDb(),
            )
        }

        AsyncFunction("stopListening") { promise: Promise ->
            try {
                // A deliberate close is a disarm, not a failure: the trigger
                // must not sit armed on a microphone that is gone.
                idle?.disarm()
                ListeningService.onStopRequested = null
                recorder?.stopListening()
                appContext.reactContext?.let { ListeningService.stop(it) }
                promise.resolve(null)
            } catch (e: Exception) {
                promise.reject("ERR_LISTEN_STOP", e.message, e)
            }
        }

        /** Every microphone currently attached, for the Settings picker. */
        /**
         * Which microphones are attached.
         *
         * Async, and it was not: this walks AudioManager, which talks to the
         * audio HAL, and a synchronous Function runs it on the JS thread. Every
         * press of Record called it, and every start and stop after that — so a
         * busy or contended HAL froze the interface at exactly the moment
         * somebody was trying to record.
         */
        AsyncFunction("listInputs") {
            val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
            return@AsyncFunction AudioInputs.list(ctx)
        }

        AsyncFunction("startRecording") { options: RecordingOptions?, promise: Promise ->
            try {
                val rate = options?.sampleRate ?: 48000
                val path = recorder().start(
                    rate,
                    options?.input,
                    { level -> sendEvent("onAudioLevel", mapOf("level" to level)) },
                    options?.prefix ?: OrphanCaptures.CAPTURE_PREFIX,
                )
                // Whoever started it. The machine claims a recording it asked
                // for; anything else — the recordist, a dictation — suspends
                // the trigger rather than being auto-stopped by it.
                idle?.recordingStarted()
                promise.resolve(path)
            } catch (e: Exception) {
                promise.reject("ERR_RECORD_START", e.message, e)
            }
        }

        AsyncFunction("probeAudioSources") { options: ProbeOptions?, promise: Promise ->
            try {
                val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
                val probeOptions = options ?: ProbeOptions()
                val report = AudioSourceProbe(ctx).run(
                    probeOptions.sampleRate,
                    probeOptions.millisPerSource,
                    probeOptions.keepAudio,
                )
                promise.resolve(report)
            } catch (e: Exception) {
                promise.reject("ERR_PROBE", e.message, e)
            }
        }

        AsyncFunction("stopRecording") { promise: Promise ->
            try {
                val summary = recorder().stop()
                idle?.recordingStopped()
                promise.resolve(summary)
            } catch (e: Exception) {
                promise.reject("ERR_RECORD_STOP", e.message, e)
            }
        }

        /**
         * Audio left behind by a process that died mid-recording.
         *
         * `known` is every audio path the database holds, so a live capture and
         * anything already entered are excluded by the caller rather than by a
         * guess here. See OrphanCaptures for why this exists at all.
         */
        AsyncFunction("recoverOrphans") { known: List<String>, promise: Promise ->
            try {
                val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
                // The live file too, in case a recording is running while this
                // is called — the DB does not know about it yet.
                val exclude = known.toMutableSet()
                recorder?.currentPath()?.let { exclude += it }
                promise.resolve(
                    OrphanCaptures.scan(ctx.cacheDir, exclude, 48000, frameBytes = 2),
                )
            } catch (e: Exception) {
                promise.reject("ERR_RECOVER", e.message, e)
            }
        }

        AsyncFunction("acquireMediaButton") { promise: Promise ->
            try {
                acquireMediaButton()
                promise.resolve(null)
            } catch (e: Exception) {
                promise.reject("ERR_MEDIA_BUTTON", e.message, e)
            }
        }

        AsyncFunction("releaseMediaButton") { promise: Promise ->
            try {
                releaseMediaButton()
                promise.resolve(null)
            } catch (e: Exception) {
                promise.reject("ERR_MEDIA_BUTTON", e.message, e)
            }
        }

        /**
         * Claim or release the volume keys as a shutter, for Bluetooth camera
         * remotes — HID keyboards hardwired to send VOLUME_UP. Foreground
         * only by nature: the keys arrive through the Activity, so a pocket
         * trigger stays the MediaSession's job. While claimed, the phone's
         * own rocker toggles recording too, and nothing in the app changes
         * the volume — that trade is the setting's to make, not this call's.
         */
        Function("setVolumeShutter") { enabled: Boolean ->
            VolumeShutterState.enabled = enabled
            VolumeShutterState.onPress = if (enabled) ::shutterPress else null
        }

        /**
         * Whether a Bluetooth output is connected right now. Async like
         * listInputs, and for the same reason: getDevices walks the audio HAL.
         */
        AsyncFunction("hasBluetoothOutput") {
            val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
            return@AsyncFunction CuePlayer(ctx).bluetoothOutputConnected()
        }

        /**
         * Say the recorder's state into the ears on two independent cadences;
         * zero for a state means that heartbeat is off.
         *
         * The intervals are the recordist's to choose in Settings, and they
         * differ on purpose: "is the buffer still alive" is an all-walk
         * question a minute apart, "am I still recording" only matters for
         * the length of a capture and wants answering every few seconds.
         */
        AsyncFunction("setHeartbeat") { options: HeartbeatOptions, promise: Promise ->
            try {
                startHeartbeats(
                    listeningMs = (options.listeningSeconds * 1000).toLong(),
                    recordingMs = (options.recordingSeconds * 1000).toLong(),
                )
                promise.resolve(null)
            } catch (e: Exception) {
                promise.reject("ERR_HEARTBEAT", e.message, e)
            }
        }

        /** Confirm through the ears what just happened — see Cue and CuePlayer. */
        AsyncFunction("playCue") { kind: String, promise: Promise ->
            try {
                val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
                val cue = Cue.from(kind)
                    ?: throw IllegalArgumentException("unknown cue: $kind")
                CuePlayer(ctx).play(cue)
                promise.resolve(null)
            } catch (e: Exception) {
                promise.reject("ERR_CUE", e.message, e)
            }
        }

        /**
         * Play the disconnect cue on demand, and say what came out.
         *
         * Because the real trigger needs the Rode, a session, and the nerve to
         * pull a microphone off mid-recording — and because when it did stay
         * silent in the field there was no way to ask the phone whether it
         * *could* have spoken. This answers that in five seconds on a desk:
         * "words" is the whole path working, "tone" says the player refused to
         * start the bundled recording, "buzz" says nothing is connected to
         * hear it with.
         */
        AsyncFunction("testDisconnectCue") { throughSpeaker: Boolean?, promise: Promise ->
            try {
                val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
                val announced = SpokenCue.MIC_DISCONNECTED.announce(
                    ctx,
                    // In the field the words are held back from the phone's own
                    // speaker, because they would land in the recording. On a
                    // desk with no earbuds paired that rule is the entire reason
                    // the test appears to do nothing, so it can be lifted here.
                    requireEarbuds = throughSpeaker != true,
                )
                promise.resolve(announced.said.name.lowercase())
            } catch (e: Exception) {
                promise.reject("ERR_CUE", e.message, e)
            }
        }

        /**
         * What the cue system would do right now, without making a sound.
         *
         * The screen leads with this because it explains most of the silence on
         * its own: every cue this app plays is held back from the phone's own
         * speaker, so with nothing paired the answer to every test is a
         * vibration the recordist may not even feel.
         */
        AsyncFunction("cueOutputState") {
            val ctx = appContext.reactContext ?: throw Exceptions.ReactContextLost()
            return@AsyncFunction mapOf(
                "bluetoothOutput" to CuePlayer(ctx).bluetoothOutputConnected(),
            )
        }

        OnDestroy {
            // A reloaded JS bundle builds a fresh module; anything left behind
            // by the old one would run on unfindable — a MediaSession holding
            // the button with nothing listening, a capture thread looping on a
            // session nothing can retire, a notification claiming a microphone
            // the fresh module cannot even see to close.
            releaseMediaButton()
            // The key handler outlives the module — it belongs to the
            // Activity — so its sink must not point at a dead emitter. The
            // fresh module's JS re-asserts the setting at startup.
            VolumeShutterState.enabled = false
            VolumeShutterState.onPress = null
            ListeningService.onStopRequested = null
            stopHeartbeats()
            idle?.destroy()
            idle = null
            stopWatchingInputs()
            recorder?.destroy()
            recorder = null
            appContext.reactContext?.let { ListeningService.stop(it) }
        }
    }
}
