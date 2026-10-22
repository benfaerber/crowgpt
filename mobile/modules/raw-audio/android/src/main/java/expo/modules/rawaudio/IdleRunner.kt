package expo.modules.rawaudio

import android.os.Handler
import android.os.Looper
import android.os.SystemClock

/**
 * One armed idle session: the trigger machine fed by the capture thread,
 * with its commands marshalled onto the main looper.
 *
 * Lives apart from [RawAudioModule] the way [BackgroundHold] and
 * [MicrophoneSwap] do — the module wires it to events and the notification,
 * this owns the threading. The capture thread calls [onPcm]; the module queue
 * calls everything else; the machine itself is the lock, because a disarm and
 * a buffer landing together must serialise or the machine's phase tears.
 *
 * Clocks are [SystemClock.elapsedRealtime] throughout: uptimeMillis stops in
 * deep sleep, and an hour-long deadline measured with it would stretch by
 * however long the phone dozed.
 */
internal class IdleRunner(
    private val config: IdleTrigger.Config,
    sampleRate: Int,
    private val onCommand: (IdleTrigger.Command) -> Unit,
) {
    private val machine = IdleTrigger(config, SystemClock.elapsedRealtime())
    private val band = BandEnergy(sampleRate)
    private val floor = NoiseFloor()
    private val handler = Handler(Looper.getMainLooper())

    /**
     * What the trigger last saw, for the screen's live meter. Volatile and
     * approximate on purpose — the UI polls once a second and a torn read of
     * a level display costs nothing. "Finicky and mute" was the first field
     * test's verdict, and these three numbers are the cure: what it hears,
     * what it calls quiet, and the line it fires over.
     */
    @Volatile
    var lastBandDb: Double = BandEnergy.FLOOR_DB
        private set

    @Volatile
    var lastFloorDb: Double = 0.0
        private set

    fun thresholdDb(): Double = maxOf(lastFloorDb + config.triggerDb, config.minDb)

    /** The deadline check, compared by identity — the heartbeat idiom. */
    @Volatile
    private var deadlineTick: Runnable? = null

    init {
        scheduleDeadline()
    }

    val phase: IdleTrigger.Phase get() = machine.phase

    val capturesMade: Int get() = machine.capturesMade

    fun remainingMs(): Long =
        (machine.deadlineMs - SystemClock.elapsedRealtime()).coerceAtLeast(0)

    /**
     * One read's worth of PCM, on the capture thread. The filter and the
     * floor live on this thread only; the machine is shared and locked.
     */
    fun onPcm(buffer: ByteArray, read: Int) {
        val bandDb = band.bandDbfs(buffer, read)
        // Judged against the floor as it stood BEFORE this buffer, and the
        // verdict fed back so the floor mostly ignores the calls themselves —
        // see NoiseFloor for the self-masking failure this order prevents.
        val floorDb = floor.floorDb()
        val hot = IdleTrigger.isHot(bandDb, floorDb, config)
        floor.record(bandDb, hot)
        lastBandDb = bandDb
        lastFloorDb = floorDb
        dispatch(synchronized(machine) {
            machine.buffer(bandDb, floorDb, SystemClock.elapsedRealtime())
        })
    }

    fun recordingStarted() {
        dispatch(synchronized(machine) {
            machine.recordingStarted(SystemClock.elapsedRealtime())
        })
    }

    fun recordingStopped() {
        dispatch(synchronized(machine) {
            machine.recordingStopped(SystemClock.elapsedRealtime())
        })
    }

    fun sessionFailed() {
        dispatch(synchronized(machine) { machine.sessionFailed() })
    }

    fun disarm() {
        dispatch(synchronized(machine) {
            machine.disarm(SystemClock.elapsedRealtime())
        })
    }

    /** Stops the timer. Already-posted commands still run; the module guards
     *  against a retired runner's stragglers by comparing identity. */
    fun destroy() {
        deadlineTick?.let { handler.removeCallbacks(it) }
        deadlineTick = null
    }

    /**
     * Buffers drive the clock while the microphone is alive, so this timer is
     * the fallback for the deadline landing in a dead-quiet stretch — and for
     * a capture spanning it, where the disarm waits on the recording's own
     * end and this re-checks until it happens.
     */
    private fun scheduleDeadline() {
        val tick = object : Runnable {
            override fun run() {
                if (deadlineTick !== this) return
                dispatch(synchronized(machine) {
                    machine.tick(SystemClock.elapsedRealtime())
                })
                if (machine.phase != IdleTrigger.Phase.DISARMED) {
                    handler.postDelayed(this, RECHECK_MS)
                }
            }
        }
        deadlineTick = tick
        handler.postDelayed(tick, remainingMs() + 500)
    }

    private fun dispatch(commands: List<IdleTrigger.Command>) {
        if (commands.isEmpty()) return
        handler.post { commands.forEach(onCommand) }
    }

    companion object {
        /** How often the fallback re-checks once the deadline has passed. */
        const val RECHECK_MS = 30_000L
    }
}
