package expo.modules.rawaudio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NoiseFloorTest {

    private val config = IdleTrigger.Config(
        armSeconds = 3600, holdSeconds = 25, maxCaptureSeconds = 600,
        maxCaptures = 20, triggerDb = 12.0, minDb = -55.0,
    )

    @Test
    fun `before anything is heard the floor is the loudest possible answer`() {
        // An armed phone spends its first seconds measuring the evening; a
        // floor of zero dBFS means nothing can trigger until it has.
        assertEquals(0.0, NoiseFloor().floorDb(), 0.0)
    }

    @Test
    fun `the floor follows the evening`() {
        val floor = NoiseFloor()
        repeat(240) { floor.record(-75.0) }
        assertEquals(-75.0, floor.floorDb(), 0.1)
        // Traffic dies off at dusk: two quieter minutes move the estimate.
        repeat(240) { floor.record(-85.0) }
        assertEquals(-85.0, floor.floorDb(), 0.1)
    }

    @Test
    fun `arming under a calling bout cannot mask the calls for long`() {
        // The first field test's failure, pinned: calls playing from the
        // moment of arming filled the window, the floor rode up toward them,
        // and floor-plus-twelve sat above the very sound it existed to catch.
        // With hot buffers held out of the window, the first quiet stretch
        // sets the floor and the calls stay 12 dB clear of it.
        val floor = NoiseFloor()
        // Ten seconds of room tone — all the quiet the estimate needs.
        repeat(20) { floor.record(-70.0, hot = IdleTrigger.isHot(-70.0, floor.floorDb(), config)) }
        // Then two solid minutes of calls, judged hot against the settled
        // floor and therefore mostly excluded from it.
        repeat(240) { floor.record(-45.0, hot = IdleTrigger.isHot(-45.0, floor.floorDb(), config)) }
        assertEquals(-70.0, floor.floorDb(), 0.1)
        assertTrue(IdleTrigger.isHot(-45.0, floor.floorDb(), config))
    }

    @Test
    fun `a street that gets permanently louder still raises the floor`() {
        // The leak: one hot buffer in ten lands anyway, so a real shift —
        // a storm arriving, not a bout — works its way in over minutes
        // rather than being refused forever.
        val floor = NoiseFloor()
        repeat(240) { floor.record(-80.0) }
        repeat(240 * NoiseFloor.HOT_SAMPLE_EVERY) { floor.record(-60.0, hot = true) }
        assertEquals(-60.0, floor.floorDb(), 0.1)
    }

    @Test
    fun `only the last two minutes count`() {
        val floor = NoiseFloor(capacity = 10)
        repeat(10) { floor.record(-90.0) }
        repeat(10) { floor.record(-70.0) }
        // The quiet spell has scrolled out of the window entirely.
        assertEquals(-70.0, floor.floorDb(), 0.1)
    }
}
