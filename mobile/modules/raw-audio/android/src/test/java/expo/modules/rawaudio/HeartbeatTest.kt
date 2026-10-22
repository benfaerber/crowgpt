package expo.modules.rawaudio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Each heartbeat timer's one honest answer per state. The dangerous cases are
 * the silent ones: an idle tick that beeped would turn "silently dead" — the
 * very failure the cue exists to expose — back into "still fine", and neither
 * timer may speak for the other's state.
 */
class HeartbeatTest {

    @Test
    fun `the listening timer ticks while the buffer is open`() {
        assertEquals(Cue.LISTENING, Heartbeat.listeningTick(recording = false, listening = true))
    }

    @Test
    fun `the listening timer is silent during a capture, not borrowed`() {
        // A tick saying "listening" mid-capture would be the cue claiming a
        // state the recorder is not in — the recording timer owns that state.
        assertNull(Heartbeat.listeningTick(recording = true, listening = false))
        // And with raw flags disagreeing (isListening() already excludes
        // recording, but a caller may pass `active`): recording still wins.
        assertNull(Heartbeat.listeningTick(recording = true, listening = true))
    }

    @Test
    fun `the recording timer beeps only while writing`() {
        assertEquals(Cue.RECORDING, Heartbeat.recordingTick(recording = true))
        assertNull(Heartbeat.recordingTick(recording = false))
    }

    @Test
    fun `idle says nothing on either timer`() {
        assertNull(Heartbeat.listeningTick(recording = false, listening = false))
        assertNull(Heartbeat.recordingTick(recording = false))
    }

    @Test
    fun `the heartbeat cues resolve from their JS names like the others do`() {
        assertEquals(Cue.LISTENING, Cue.from("listening"))
        assertEquals(Cue.RECORDING, Cue.from("recording"))
    }
}
