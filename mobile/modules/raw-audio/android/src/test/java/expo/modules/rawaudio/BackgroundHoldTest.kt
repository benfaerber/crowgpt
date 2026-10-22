package expo.modules.rawaudio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The wish for pocket listening survives being refused.
 *
 * The bug this guards against needed a pocket and a route change to see: a
 * `setBackground` landing while the session was between a stop and a start
 * was answered "no" from the closed session and nothing ever retried, so
 * pocket listening believed it was on while no foreground service held the
 * process — which is reapable, and got reaped, taking the earbud button with
 * it. The repair is `reassert` after every session (re)open, and these
 * sequences are the ones a phone cannot be asked to reproduce on demand.
 */
class BackgroundHoldTest {

    private class Fixture(var isListening: Boolean = true) {
        val calls = mutableListOf<String>()
        var running = false
        val hold = BackgroundHold(
            listening = { isListening },
            serviceRunning = { running },
            startService = {
                calls += "start"
                running = true
            },
            stopService = {
                calls += "stop"
                running = false
            },
        )
    }

    @Test
    fun `wanting it while listening starts the service`() {
        val fixture = Fixture()
        assertTrue(fixture.hold.set(true))
        assertEquals(listOf("start"), fixture.calls)
    }

    @Test
    fun `wanting it between sessions starts nothing and says so`() {
        val fixture = Fixture(isListening = false)
        assertFalse(fixture.hold.set(true))
        assertEquals(emptyList<String>(), fixture.calls)
    }

    @Test
    fun `the refused wish is granted when the session reopens`() {
        // The whole bug: this used to require the setting to be toggled again.
        val fixture = Fixture(isListening = false)
        fixture.hold.set(true)
        fixture.isListening = true
        assertTrue(fixture.hold.reassert())
        assertEquals(listOf("start"), fixture.calls)
    }

    @Test
    fun `not wanting it stops the service`() {
        val fixture = Fixture()
        fixture.hold.set(true)
        assertFalse(fixture.hold.set(false))
        assertEquals(listOf("start", "stop"), fixture.calls)
    }

    @Test
    fun `mid-swap the service is not stopped for a closed session`() {
        // MicrophoneSwap's rule seen from this side: the service deliberately
        // outlives the session across a swap, and a reassert in that window
        // must leave it alone or every route change ends pocket listening.
        val fixture = Fixture()
        fixture.hold.set(true)
        fixture.isListening = false
        assertFalse(fixture.hold.reassert())
        assertEquals(listOf("start"), fixture.calls)
        assertTrue(fixture.running)
    }

    @Test
    fun `a reassert over a running service starts nothing twice`() {
        val fixture = Fixture()
        fixture.hold.set(true)
        assertTrue(fixture.hold.reassert())
        assertEquals(listOf("start"), fixture.calls)
    }

    @Test
    fun `expect records the wish without touching the service`() {
        // startListening's path: the service must start before the session
        // opens, so it cannot go through reassert — but the wish still has to
        // be on record for every later reassert to act on.
        val fixture = Fixture(isListening = false)
        fixture.hold.expect(true)
        assertEquals(emptyList<String>(), fixture.calls)
        fixture.isListening = true
        assertTrue(fixture.hold.reassert())
        assertEquals(listOf("start"), fixture.calls)
    }

    @Test
    fun `an unwanted reassert with nothing running stops nothing`() {
        val fixture = Fixture()
        assertFalse(fixture.hold.reassert())
        assertEquals(emptyList<String>(), fixture.calls)
    }
}
