package expo.modules.rawaudio

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The recency contest, played out as the sequences a walk produces.
 *
 * The button follows whichever uid played audio last, so every change in what
 * is playing is a moment the contest can be lost — and our own silent blip must
 * not count as "other audio", or asserting once would mean asserting forever.
 *
 * The rule changed after a field test: re-asserting only when everything went
 * quiet meant an app that never stops was never contested. Spotify held the
 * button for a whole walk that way.
 */
class ReclaimDeciderTest {

    /**
     * Never while they are playing. A blip mid-playback cannot win the election
     * — a still-playing app is still the most recent — and it leaves this app
     * holding a live player, which is the exact condition that gets a uid faded
     * out of the playback monitor permanently when the other app takes focus.
     */
    @Test
    fun `audio starting is not contested`() {
        val decider = ReclaimDecider()
        assertFalse("blipping now is how the fade latches", decider.onPlayersChanged(1, 0, 0))
    }

    @Test
    fun `a YouTube video ending hands the button back`() {
        val decider = ReclaimDecider()
        decider.onPlayersChanged(1, 0, 0)
        assertTrue("the moment it stops, re-assert", decider.onPlayersChanged(0, 0, 10_000))
    }

    @Test
    fun `music playing on and on is left alone`() {
        val decider = ReclaimDecider()
        decider.onPlayersChanged(1, 0, 0)
        assertFalse(decider.onPlayersChanged(2, 0, 10_000))
        assertFalse(decider.onPlayersChanged(3, 0, 20_000))
        assertTrue("only when it finally stops", decider.onPlayersChanged(0, 0, 30_000))
    }

    @Test
    fun `our own blip never triggers another blip`() {
        // The infinite loop this class exists to not have: the blip is itself
        // a playback config change, in both directions.
        val decider = ReclaimDecider()
        assertFalse(decider.onPlayersChanged(1, 1, 0))
        assertFalse(decider.onPlayersChanged(0, 0, 10_000))
    }

    @Test
    fun `a level that has not changed is not a new contest`() {
        val decider = ReclaimDecider()
        assertFalse(decider.onPlayersChanged(1, 0, 0))
        assertFalse("still the same music playing", decider.onPlayersChanged(2, 0, 10_000))
    }

    @Test
    fun `the cooldown bounds the rate however many reasons arrive`() {
        val decider = ReclaimDecider(cooldownMs = 2_000)
        decider.onPlayersChanged(1, 0, 0)
        assertTrue(decider.onPlayersChanged(0, 0, 1_000))
        decider.onPlayersChanged(1, 0, 1_500)
        assertFalse("too soon after the last", decider.onPlayersChanged(0, 0, 2_000))
        decider.onPlayersChanged(1, 0, 8_000)
        assertTrue(decider.onPlayersChanged(0, 0, 9_000))
    }

    @Test
    fun `a quiet phone needs nothing`() {
        assertFalse(ReclaimDecider().onPlayersChanged(0, 0, 0))
    }
}

/**
 * One tap has to produce one toggle, and the phone has two ways to report it.
 *
 * A press that starts a recording and immediately stops it is indistinguishable
 * from a press that did nothing, which is what "the button works sometimes"
 * actually looks like from the outside.
 */
class PressGateTest {

    @Test
    fun `one press counts`() {
        assertTrue(PressGate().accept(1_000))
    }

    @Test
    fun `the same tap arriving twice counts once`() {
        val gate = PressGate()
        assertTrue(gate.accept(1_000))
        assertFalse("key event and transport control for one tap", gate.accept(1_020))
    }

    @Test
    fun `a play pause pair from one tap counts once`() {
        val gate = PressGate()
        assertTrue(gate.accept(5_000))
        assertFalse(gate.accept(5_005))
        assertFalse(gate.accept(5_100))
    }

    @Test
    fun `a deliberate second press still counts`() {
        val gate = PressGate()
        assertTrue(gate.accept(1_000))
        assertTrue("start, then stop a moment later", gate.accept(1_800))
    }

    @Test
    fun `presses far apart all count`() {
        val gate = PressGate()
        assertTrue(gate.accept(0))
        assertTrue(gate.accept(60_000))
        assertTrue(gate.accept(120_000))
    }
}
