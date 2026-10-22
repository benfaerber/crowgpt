package expo.modules.rawaudio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The trigger driven through the same scenarios as idle.test.ts, because
 * this class and domain/idle.ts are one machine written twice — the vitest
 * copy renders the UI, this one runs the hour — and the only defence against
 * the two drifting is that both test suites tell the same story.
 */
class IdleTriggerTest {

    private val t0 = 1_000_000L
    private val quiet = -70.0
    private val floor = -75.0
    private val caw = -40.0

    private fun config(
        armSeconds: Int = 3600,
        holdSeconds: Int = 25,
        maxCaptureSeconds: Int = 600,
        maxCaptures: Int = 20,
    ) = IdleTrigger.Config(
        armSeconds = armSeconds,
        holdSeconds = holdSeconds,
        maxCaptureSeconds = maxCaptureSeconds,
        maxCaptures = maxCaptures,
        triggerDb = 12.0,
        minDb = -55.0,
    )

    private fun recording(config: IdleTrigger.Config = config()): Pair<IdleTrigger, Long> {
        val trigger = IdleTrigger(config, t0)
        trigger.buffer(caw, floor, t0)
        trigger.recordingStarted(t0 + 500)
        return trigger to (t0 + 500)
    }

    @Test
    fun `a buffer twelve dB over the floor is a call, under the absolute gate is not`() {
        val cfg = config()
        assertTrue(IdleTrigger.isHot(-47.0, -60.0, cfg))
        assertTrue(!IdleTrigger.isHot(-48.0, -60.0, cfg))
        // Floor at -90: floor + 12 = -78, but nothing under -55 dBFS counts.
        assertTrue(!IdleTrigger.isHot(-60.0, -90.0, cfg))
        assertTrue(IdleTrigger.isHot(-54.0, -90.0, cfg))
    }

    @Test
    fun `one hot buffer asks for a recording`() {
        val trigger = IdleTrigger(config(), t0)
        assertEquals(emptyList<IdleTrigger.Command>(), trigger.buffer(quiet, floor, t0))
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStart),
            trigger.buffer(caw, floor, t0 + 500),
        )
        assertEquals(IdleTrigger.Phase.TRIGGERED, trigger.phase)
    }

    @Test
    fun `an unanswered start is repeated on a hot buffer, not into silence`() {
        val trigger = IdleTrigger(config(), t0)
        trigger.buffer(caw, floor, t0)
        assertTrue(trigger.buffer(caw, floor, t0 + 2_000).isEmpty())
        assertTrue(trigger.buffer(quiet, floor, t0 + IdleTrigger.REEMIT_MS).isEmpty())
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStart),
            trigger.buffer(caw, floor, t0 + IdleTrigger.REEMIT_MS + 500),
        )
    }

    @Test
    fun `the pauses inside a bout do not split it`() {
        val (trigger, started) = recording()
        var t = started
        repeat(5) {
            t += 1_500
            assertTrue(trigger.buffer(quiet, floor, t).isEmpty())
            t += 500
            assertTrue(trigger.buffer(caw, floor, t).isEmpty())
        }
        assertEquals(IdleTrigger.Phase.RECORDING, trigger.phase)
    }

    @Test
    fun `held silence ends the capture`() {
        val (trigger, started) = recording()
        assertTrue(trigger.buffer(quiet, floor, started + 24_000).isEmpty())
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStop),
            trigger.buffer(quiet, floor, started + 25_000),
        )
        assertEquals(IdleTrigger.Phase.STOPPING, trigger.phase)
    }

    @Test
    fun `a capture that will not end quietly is capped`() {
        val (trigger, started) = recording()
        assertTrue(trigger.buffer(caw, floor, started + 599_000).isEmpty())
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStop),
            trigger.buffer(caw, floor, started + 600_000),
        )
    }

    @Test
    fun `an unanswered stop is repeated whatever the level`() {
        val (trigger, started) = recording()
        trigger.buffer(quiet, floor, started + 25_000)
        assertTrue(trigger.buffer(quiet, floor, started + 27_000).isEmpty())
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStop),
            trigger.buffer(quiet, floor, started + 25_000 + IdleTrigger.REEMIT_MS),
        )
    }

    @Test
    fun `the hold counts from the recording, not the buffer that tripped it`() {
        val trigger = IdleTrigger(config(), t0)
        trigger.buffer(caw, floor, t0)
        trigger.recordingStarted(t0 + 4_000)
        assertTrue(trigger.buffer(quiet, floor, t0 + 4_000 + 24_000).isEmpty())
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStop),
            trigger.buffer(quiet, floor, t0 + 4_000 + 25_000),
        )
    }

    private fun stopped(config: IdleTrigger.Config = config()): Pair<IdleTrigger, Long> {
        val (trigger, started) = recording(config)
        trigger.buffer(quiet, floor, started + 30_000)
        trigger.recordingStopped(started + 31_000)
        return trigger to (started + 31_000)
    }

    @Test
    fun `the cooldown lets the ring refill before the next trigger`() {
        val (trigger, at) = stopped()
        assertEquals(IdleTrigger.Phase.COOLDOWN, trigger.phase)
        assertTrue(trigger.buffer(caw, floor, at + IdleTrigger.COOLDOWN_MS - 1_000).isEmpty())
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStart),
            trigger.buffer(caw, floor, at + IdleTrigger.COOLDOWN_MS),
        )
    }

    @Test
    fun `the capture cap disarms rather than carrying on`() {
        val (trigger, at) = stopped(config(maxCaptures = 2))
        assertEquals(1, trigger.capturesMade)
        val t = at + IdleTrigger.COOLDOWN_MS
        trigger.buffer(caw, floor, t)
        trigger.recordingStarted(t + 500)
        trigger.buffer(quiet, floor, t + 30_000)
        val commands = trigger.recordingStopped(t + 31_000)
        assertEquals(
            IdleTrigger.Command.Disarmed(IdleTrigger.DisarmReason.CAPTURE_CAP),
            commands.first(),
        )
        assertEquals(IdleTrigger.Phase.DISARMED, trigger.phase)
    }

    @Test
    fun `a recording the machine did not ask for suspends the trigger`() {
        val trigger = IdleTrigger(config(), t0)
        trigger.recordingStarted(t0 + 1_000)
        assertEquals(IdleTrigger.Phase.SUSPENDED, trigger.phase)
        assertTrue(trigger.buffer(quiet, floor, t0 + 120_000).isEmpty())
        trigger.recordingStopped(t0 + 130_000)
        assertEquals(0, trigger.capturesMade)
        assertEquals(IdleTrigger.Phase.ARMED, trigger.phase)
    }

    @Test
    fun `disarming mid-capture files the bird before standing down`() {
        val (trigger, started) = recording()
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStop),
            trigger.disarm(started + 5_000),
        )
        val commands = trigger.recordingStopped(started + 6_000)
        assertEquals(
            IdleTrigger.Command.Disarmed(IdleTrigger.DisarmReason.MANUAL),
            commands.first(),
        )
    }

    @Test
    fun `the deadline stands the session down`() {
        val trigger = IdleTrigger(config(armSeconds = 3600), t0)
        assertTrue(trigger.tick(t0 + 3_599_000).isEmpty())
        assertEquals(
            IdleTrigger.Command.Disarmed(IdleTrigger.DisarmReason.EXPIRED),
            trigger.tick(t0 + 3_600_000).first(),
        )
    }

    @Test
    fun `a capture spanning the deadline finishes on its own terms`() {
        val trigger = IdleTrigger(config(armSeconds = 3600), t0)
        val late = t0 + 3_599_000
        trigger.buffer(caw, floor, late)
        trigger.recordingStarted(late + 500)
        assertTrue(trigger.tick(t0 + 3_600_000).isEmpty())
        assertEquals(IdleTrigger.Phase.RECORDING, trigger.phase)
        assertEquals(
            listOf<IdleTrigger.Command>(IdleTrigger.Command.EmitStop),
            trigger.buffer(quiet, floor, late + 500 + 25_000),
        )
        assertEquals(
            IdleTrigger.Command.Disarmed(IdleTrigger.DisarmReason.EXPIRED),
            trigger.recordingStopped(late + 500 + 26_000).first(),
        )
    }

    @Test
    fun `a dead session disarms from any state`() {
        val (trigger, _) = recording()
        assertEquals(
            IdleTrigger.Command.Disarmed(IdleTrigger.DisarmReason.SESSION_FAILED),
            trigger.sessionFailed().first(),
        )
        assertTrue(trigger.buffer(caw, floor, t0 + 60_000).isEmpty())
        assertTrue(trigger.sessionFailed().isEmpty())
    }
}
