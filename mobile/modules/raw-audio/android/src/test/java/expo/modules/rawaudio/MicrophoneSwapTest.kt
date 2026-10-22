package expo.modules.rawaudio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The swap's one rule: the foreground service survives it.
 *
 * The bug this guards against was a backgrounded route change — earbuds
 * resuming Spotify — where the swap went through stopListening, took the
 * service down, and could not start it again from the background. These
 * sequences are exactly the ones that need a phone, music, and a pocket to
 * reproduce, which is why the rule lives in a class a JVM test can drive.
 */
class MicrophoneSwapTest {

    private class Fixture(
        private val isListening: Boolean = true,
        private val openFails: Boolean = false,
        private val closeFails: Boolean = false,
    ) {
        val calls = mutableListOf<String>()
        val swap = MicrophoneSwap(
            listening = { isListening },
            closeSession = {
                calls += "close"
                if (closeFails) throw IllegalStateException("previous thread still running")
            },
            openSession = {
                calls += "open"
                if (openFails) throw IllegalStateException("AudioRecord init failed")
            },
            standDownService = { calls += "standDown" },
        )
    }

    @Test
    fun `a swap closes and reopens the session and never touches the service`() {
        val fixture = Fixture()
        fixture.swap.swap()
        assertEquals(listOf("close", "open"), fixture.calls)
    }

    @Test
    fun `nothing listening is a refusal, not a half-open microphone`() {
        val fixture = Fixture(isListening = false)
        val refusal = runCatching { fixture.swap.swap() }
        assertTrue(refusal.exceptionOrNull() is IllegalStateException)
        // A swap that did not begin must not have closed, opened, or stopped
        // anything — a recording in progress reads as not-listening too.
        assertEquals(emptyList<String>(), fixture.calls)
    }

    @Test
    fun `a reopen that fails stands the service down and still fails loudly`() {
        val fixture = Fixture(openFails = true)
        val failure = runCatching { fixture.swap.swap() }
        assertTrue(failure.isFailure)
        // The microphone is closed and did not reopen: leaving the service up
        // would hold a notification claiming a microphone nobody has.
        assertEquals(listOf("close", "open", "standDown"), fixture.calls)
    }

    @Test
    fun `a close that fails stands the service down too`() {
        val fixture = Fixture(closeFails = true)
        val failure = runCatching { fixture.swap.swap() }
        assertTrue(failure.isFailure)
        assertEquals(listOf("close", "standDown"), fixture.calls)
    }
}
