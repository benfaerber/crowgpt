package expo.modules.rawaudio

/**
 * Idle mode's trigger: armed for an hour, starts a capture when the crow
 * band gets loud, stops it after held silence, stands down when the hour ends.
 *
 * This is the authoritative copy — it runs on the capture thread's buffers,
 * because every decision here is a timing decision and JS timers pause with
 * the screen, which is exactly the state an unattended phone is in. The
 * transition table is mirrored line for line in mobile/src/domain/idle.ts,
 * and IdleTriggerTest.kt repeats the vitest scenarios so drift between the
 * two is a failing test rather than a field discovery.
 *
 * The machine never touches the recorder. It returns commands — emit a start,
 * emit a stop, say the session is over — and [RawAudioModule] carries them
 * out, which is what lets a JVM test drive it through an hour nobody wants to
 * stand through. Pure Kotlin, no Android imports, like [SessionState].
 */
internal class IdleTrigger(private val config: Config, now: Long) {

    /** Mirrors IdleConfig in domain/idle.ts; see there for each bound's
     *  reasoning. All values arrive clamped by the settings screen. */
    data class Config(
        val armSeconds: Int,
        val holdSeconds: Int,
        val maxCaptureSeconds: Int,
        val maxCaptures: Int,
        val triggerDb: Double,
        val minDb: Double,
    )

    enum class Phase { ARMED, TRIGGERED, RECORDING, STOPPING, COOLDOWN, SUSPENDED, DISARMED }

    enum class DisarmReason { EXPIRED, CAPTURE_CAP, SESSION_FAILED, MANUAL }

    enum class NotifyState { ARMED, RECORDING, REVERTED }

    sealed class Command {
        object EmitStart : Command()
        object EmitStop : Command()
        data class Disarmed(val reason: DisarmReason) : Command()
        data class Notify(val state: NotifyState) : Command()
    }

    @Volatile
    var phase = Phase.ARMED
        private set

    @Volatile
    var disarmReason: DisarmReason? = null
        private set

    @Volatile
    var capturesMade = 0
        private set

    val deadlineMs: Long = now + config.armSeconds * 1000L

    private var recordStartedAt = 0L
    private var lastHotAt = 0L
    private var lastEmitAt = 0L
    private var cooldownUntil = 0L
    /** The hour ended while a capture was in flight; it finishes on its own
     *  hold or cap, and the session ends with it. */
    private var disarmAtEnd = false

    /** Half a second of band energy, against the floor measured alongside it. */
    fun buffer(bandDb: Double, floorDb: Double, now: Long): List<Command> {
        val expired = checkDeadline(now)
        if (expired.isNotEmpty() || phase == Phase.DISARMED) return expired

        val hot = isHot(bandDb, floorDb, config)
        return when (phase) {
            Phase.ARMED -> {
                if (!hot) return emptyList()
                phase = Phase.TRIGGERED
                lastHotAt = now
                emit(now, Command.EmitStart)
            }
            Phase.TRIGGERED -> {
                // The start is out but the recording has not begun. Only a hot
                // buffer re-emits: a start repeated into silence would begin a
                // capture of nothing, five seconds after whatever tripped the
                // first one ended.
                if (hot) lastHotAt = now
                if (hot && now - lastEmitAt >= REEMIT_MS) emit(now, Command.EmitStart)
                else emptyList()
            }
            Phase.RECORDING -> {
                if (hot) lastHotAt = now
                val overLong = now - recordStartedAt >= config.maxCaptureSeconds * 1000L
                val heldSilence = now - lastHotAt >= config.holdSeconds * 1000L
                if (overLong || heldSilence) {
                    phase = Phase.STOPPING
                    emit(now, Command.EmitStop)
                } else {
                    emptyList()
                }
            }
            Phase.STOPPING ->
                // Any buffer re-emits here, unlike TRIGGERED: the stop is about
                // a recording that is demonstrably still running, whatever the
                // level.
                if (now - lastEmitAt >= REEMIT_MS) emit(now, Command.EmitStop)
                else emptyList()
            Phase.COOLDOWN -> {
                if (now < cooldownUntil) return emptyList()
                phase = Phase.ARMED
                // Re-enter: this buffer may itself be the next call.
                buffer(bandDb, floorDb, now)
            }
            Phase.SUSPENDED -> emptyList()
            Phase.DISARMED -> emptyList()
        }
    }

    /**
     * A recording began. Claimed when this machine asked for one; anything
     * else is the recordist's own capture, which suspends the trigger — a
     * deliberate recording must never be ended by an algorithm's idea of
     * silence.
     */
    fun recordingStarted(now: Long): List<Command> {
        if (phase == Phase.DISARMED) return emptyList()
        if (phase == Phase.TRIGGERED) {
            phase = Phase.RECORDING
            recordStartedAt = now
            // The hold counts from the recording, not from the buffer that
            // tripped it — otherwise a slow bridge eats into the silence budget.
            lastHotAt = now
            return listOf(Command.Notify(NotifyState.RECORDING))
        }
        phase = Phase.SUSPENDED
        return emptyList()
    }

    fun recordingStopped(now: Long): List<Command> {
        if (phase == Phase.DISARMED) return emptyList()
        val mine = phase == Phase.RECORDING || phase == Phase.STOPPING
        if (mine) capturesMade += 1
        if (mine && capturesMade >= config.maxCaptures) {
            return disarmNow(DisarmReason.CAPTURE_CAP)
        }
        if (disarmAtEnd || now >= deadlineMs) {
            return disarmNow(disarmReason ?: DisarmReason.EXPIRED)
        }
        if (mine) {
            phase = Phase.COOLDOWN
            cooldownUntil = now + COOLDOWN_MS
        } else {
            phase = Phase.ARMED
        }
        return listOf(Command.Notify(NotifyState.ARMED))
    }

    /**
     * The microphone died under the session. Nothing is left to listen
     * through, so the session is over from any state — the recorder's own
     * failure path collects a partial capture if one was running.
     */
    fun sessionFailed(): List<Command> {
        if (phase == Phase.DISARMED) return emptyList()
        return disarmNow(DisarmReason.SESSION_FAILED)
    }

    /** The recordist pressed Disarm. An auto capture in flight is ended first
     *  and filed as usual — disarming must not discard a bird. */
    fun disarm(now: Long): List<Command> {
        if (phase == Phase.DISARMED) return emptyList()
        disarmReason = DisarmReason.MANUAL
        return when (phase) {
            Phase.RECORDING -> {
                disarmAtEnd = true
                phase = Phase.STOPPING
                emit(now, Command.EmitStop)
            }
            Phase.STOPPING, Phase.SUSPENDED -> {
                disarmAtEnd = true
                emptyList()
            }
            else -> disarmNow(DisarmReason.MANUAL)
        }
    }

    /** The fallback timer. Buffers drive the clock while the microphone is
     *  alive; this exists for the deadline landing in a silent stretch. */
    fun tick(now: Long): List<Command> {
        if (phase == Phase.DISARMED) return emptyList()
        return checkDeadline(now)
    }

    private fun checkDeadline(now: Long): List<Command> {
        if (now < deadlineMs || disarmAtEnd) return emptyList()
        return when (phase) {
            // TRIGGERED too: the emitted start may still be crossing the
            // bridge, but waiting for a recording that may never come would
            // hold the microphone all night. Disarming wins; a start landing
            // afterwards is ignored as any foreign recording is.
            Phase.ARMED, Phase.COOLDOWN, Phase.TRIGGERED -> disarmNow(DisarmReason.EXPIRED)
            else -> {
                // A capture is running or ending. It finishes on its own
                // terms; the session ends with it.
                disarmAtEnd = true
                disarmReason = disarmReason ?: DisarmReason.EXPIRED
                emptyList()
            }
        }
    }

    private fun disarmNow(reason: DisarmReason): List<Command> {
        phase = Phase.DISARMED
        disarmReason = disarmReason ?: reason
        return listOf(
            Command.Disarmed(disarmReason!!),
            Command.Notify(NotifyState.REVERTED),
        )
    }

    private fun emit(now: Long, command: Command): List<Command> {
        lastEmitAt = now
        return listOf(command)
    }

    companion object {
        /** See domain/idle.ts for both constants' reasoning. */
        const val REEMIT_MS = 5_000L
        const val COOLDOWN_MS = 10_000L

        /**
         * Whether one half-second of band energy counts as a call. Strictly
         * above, matching the segmenter the 12 dB came from; the absolute gate
         * keeps a silent evening's measured floor from arming a hair trigger.
         */
        fun isHot(bandDb: Double, floorDb: Double, config: Config): Boolean =
            bandDb > maxOf(floorDb + config.triggerDb, config.minDb)
    }
}
