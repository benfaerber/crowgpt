package expo.modules.rawaudio

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The ring is the one piece of the pre-roll with real logic, and its failure
 * mode is silent: a wrap computed one byte wrong doesn't crash, it shifts every
 * sample by half a frame and turns the head of the recording into static that
 * nobody notices until they listen.
 */
class PreRollTest {

    private fun bytes(vararg values: Int) = ByteArray(values.size) { values[it].toByte() }

    @Test
    fun `holds less than capacity intact`() {
        val ring = PreRoll(8)
        ring.write(bytes(1, 2, 3), 3)
        assertArrayEquals(bytes(1, 2, 3), ring.drain())
    }

    @Test
    fun `drops the oldest bytes once full`() {
        val ring = PreRoll(4)
        ring.write(bytes(1, 2, 3), 3)
        ring.write(bytes(4, 5, 6), 3)
        assertArrayEquals(bytes(3, 4, 5, 6), ring.drain())
    }

    @Test
    fun `a write that wraps stays in order`() {
        val ring = PreRoll(5)
        ring.write(bytes(1, 2, 3, 4), 4)
        ring.write(bytes(5, 6, 7), 3)
        assertArrayEquals(bytes(3, 4, 5, 6, 7), ring.drain())
    }

    @Test
    fun `a write longer than the ring keeps its tail`() {
        val ring = PreRoll(3)
        ring.write(bytes(1, 2, 3, 4, 5, 6), 6)
        assertArrayEquals(bytes(4, 5, 6), ring.drain())
    }

    @Test
    fun `only the reported length is taken from the buffer`() {
        val ring = PreRoll(8)
        // AudioRecord returns how much of the buffer it filled; the rest is
        // stale audio from the previous read and must not reach the file.
        ring.write(bytes(1, 2, 3, 9, 9), 3)
        assertArrayEquals(bytes(1, 2, 3), ring.drain())
    }

    @Test
    fun `draining empties the ring`() {
        val ring = PreRoll(4)
        ring.write(bytes(1, 2), 2)
        ring.drain()
        assertEquals(0, ring.bytesHeld)
        assertArrayEquals(ByteArray(0), ring.drain())
    }

    @Test
    fun `a zero-second buffer swallows writes instead of dividing by zero`() {
        val ring = PreRoll(PreRoll.sizeFor(0.0, 48000))
        ring.write(bytes(1, 2, 3), 3)
        assertEquals(0, ring.bytesHeld)
        assertArrayEquals(ByteArray(0), ring.drain())
    }

    @Test
    fun `capacity is whole frames of mono 16-bit audio`() {
        assertEquals(15 * 48000 * 2, PreRoll.sizeFor(15.0, 48000))
        assertEquals(0, PreRoll.sizeFor(0.0, 48000))
        assertEquals(0, PreRoll.sizeFor(-1.0, 48000))
    }
}
