package expo.modules.rawaudio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The recorder's lifecycle, driven through the sequences that broke it.
 *
 * Every bug this recorder has had was two of these flags disagreeing, and none
 * of them could be reproduced without holding a phone and being quick. That is
 * the whole reason this class exists apart from the audio.
 */
class SessionStateTest {

    @Test
    fun `a fresh recorder is doing nothing`() {
        val session = SessionState()
        assertFalse(session.active)
        assertFalse(session.recording)
        assertFalse(session.isListening())
    }

    @Test
    fun `listening holds the microphone without writing`() {
        val session = SessionState()
        session.beginListening()
        session.open(writing = false)

        assertTrue(session.isListening())
        assertFalse(session.recording)
    }

    @Test(expected = IllegalStateException::class)
    fun `a second listen is refused rather than opening a second microphone`() {
        val session = SessionState()
        session.beginListening()
        session.open(writing = false)
        session.beginListening()
    }

    @Test
    fun `recording while listening continues the same session`() {
        // The pre-roll depends on it: the ring is already full, and reopening
        // the microphone would throw away the seconds before the button.
        val session = SessionState()
        session.beginListening()
        val opened = session.open(writing = false)

        val fromRing = session.beginRecording()

        assertTrue(fromRing)
        assertTrue(session.owns(opened))
        assertTrue(session.recording)
        assertFalse(session.isListening())
    }

    @Test
    fun `recording without listening needs a session of its own`() {
        val session = SessionState()
        assertFalse(session.beginRecording())
    }

    @Test(expected = IllegalStateException::class)
    fun `record tapped twice is refused`() {
        val session = SessionState()
        session.beginRecording()
        session.open(writing = true)
        session.beginRecording()
    }

    @Test
    fun `stopping while listening keeps the microphone open`() {
        // Crows call in bouts. The second call is missed as easily as the first.
        val session = SessionState()
        session.beginListening()
        session.open(writing = false)
        session.beginRecording()

        val stillListening = session.endRecording()

        assertTrue(stillListening)
        assertTrue(session.isListening())
    }

    @Test
    fun `stopping a lone recording ends the session`() {
        val session = SessionState()
        session.beginRecording()
        session.open(writing = true)

        assertFalse(session.endRecording())
    }

    @Test(expected = IllegalStateException::class)
    fun `stopping when nothing is recording is refused`() {
        SessionState().endRecording()
    }

    @Test
    fun `a retired session stops owning itself`() {
        val session = SessionState()
        session.beginListening()
        val mine = session.open(writing = false)

        session.retire()

        assertFalse(session.owns(mine))
        assertFalse(session.active)
    }

    @Test
    fun `a thread from a retired session never owns the next one`() {
        // The bug this was written for. `active` is one flag shared by every
        // session, so a thread slow to return from a read stayed in its loop
        // while the next session set the flag back to true underneath it — two
        // threads writing interleaved buffers into one WAV.
        val session = SessionState()
        session.beginListening()
        val stale = session.open(writing = false)
        session.endListening()

        session.beginListening()
        val fresh = session.open(writing = false)

        assertTrue(session.active)
        assertFalse("a stale thread must not own the new session", session.owns(stale))
        assertTrue(session.owns(fresh))
    }

    @Test
    fun `every session gets a number of its own`() {
        val session = SessionState()
        val seen = mutableSetOf<Int>()
        repeat(5) {
            session.beginListening()
            seen += session.open(writing = false)
            session.endListening()
        }
        assertEquals(5, seen.size)
    }

    @Test
    fun `a failed listen ends the session and can be reopened`() {
        // The bug this was written for: a listening thread that died left
        // `active` true forever, so the phone claimed to be listening to a
        // microphone it no longer had — and refused to open a real one.
        val session = SessionState()
        session.beginListening()
        val mine = session.open(writing = false)

        assertTrue(session.fail(mine))

        assertFalse(session.active)
        assertFalse(session.isListening())
        session.beginListening()
        session.open(writing = false)
        assertTrue(session.isListening())
    }

    @Test
    fun `a failed recording still lets stop collect the file`() {
        val session = SessionState()
        session.beginRecording()
        val mine = session.open(writing = true)

        assertTrue(session.fail(mine))

        assertTrue("stop() must still find a recording to close", session.recording)
        assertFalse(session.endRecording())
    }

    @Test
    fun `a failure mid-recording does not hand the session back to listening`() {
        // The thread is dead; "keep listening" would be a ring nothing refills.
        val session = SessionState()
        session.beginListening()
        val mine = session.open(writing = false)
        session.beginRecording()

        assertTrue(session.fail(mine))

        assertFalse(session.endRecording())
    }

    @Test
    fun `a stale thread's death changes nothing`() {
        val session = SessionState()
        session.beginListening()
        val stale = session.open(writing = false)
        session.endListening()
        session.beginListening()
        session.open(writing = false)

        assertFalse(session.fail(stale))
        assertTrue(session.isListening())
    }

    @Test
    fun `recording after a failed listen opens its own microphone`() {
        val session = SessionState()
        session.beginListening()
        val mine = session.open(writing = false)
        session.fail(mine)

        assertFalse("the ring is dead; a fresh session must open", session.beginRecording())
    }

    @Test
    fun `listening can be stopped when it was never started`() {
        // Called from teardown paths that cannot know. Throwing here would turn
        // tidying up into a crash.
        SessionState().endListening()
    }

    @Test
    fun `a full field sequence leaves nothing running`() {
        // Open the app, buffer, record a call, keep listening, record the
        // answering call, then put the phone away.
        val session = SessionState()
        session.beginListening()
        session.open(writing = false)

        session.beginRecording()
        assertTrue(session.endRecording())

        session.beginRecording()
        assertTrue(session.endRecording())

        session.endListening()

        assertFalse(session.active)
        assertFalse(session.recording)
        assertFalse(session.isListening())
    }
}
