package expo.modules.rawaudio

/**
 * The last few seconds of sound, kept in memory so a recording can start in the
 * past.
 *
 * By the time you have heard a crow and reached the button, the call is over.
 * That is not a UI problem to be shaved down — it is the length of a human
 * reaction against the length of a caw, and the button will always lose. So the
 * microphone runs before you press it and the recording begins with what was
 * already in here.
 *
 * A plain byte ring: PCM in, PCM out, oldest overwritten. Fifteen seconds of
 * 48 kHz mono 16-bit is about 1.4 MB, which is nothing to hold and far cheaper
 * than the missed call.
 *
 * Not thread-safe on its own. [WavRecorder] owns the lock, because the capture
 * thread writes here while the UI thread may be draining it.
 */
class PreRoll(private val capacityBytes: Int) {

    private val buffer = ByteArray(capacityBytes)
    private var writePos = 0
    private var filled = 0

    val bytesHeld: Int get() = filled

    fun write(data: ByteArray, length: Int) {
        if (capacityBytes == 0 || length <= 0) return
        // A read longer than the whole ring can only leave its tail behind.
        val from = if (length > capacityBytes) length - capacityBytes else 0
        val count = length - from
        val firstChunk = minOf(count, capacityBytes - writePos)
        System.arraycopy(data, from, buffer, writePos, firstChunk)
        if (count > firstChunk) {
            System.arraycopy(data, from + firstChunk, buffer, 0, count - firstChunk)
        }
        writePos = (writePos + count) % capacityBytes
        filled = minOf(capacityBytes, filled + count)
    }

    /** Everything held, oldest first. Empties the ring. */
    fun drain(): ByteArray {
        if (filled == 0) return ByteArray(0)
        val out = ByteArray(filled)
        val start = (writePos - filled + capacityBytes) % capacityBytes
        val firstChunk = minOf(filled, capacityBytes - start)
        System.arraycopy(buffer, start, out, 0, firstChunk)
        if (filled > firstChunk) {
            System.arraycopy(buffer, 0, out, firstChunk, filled - firstChunk)
        }
        clear()
        return out
    }

    fun clear() {
        writePos = 0
        filled = 0
    }

    companion object {
        /** Bytes needed to hold `seconds` of mono 16-bit audio at `sampleRate`. */
        fun sizeFor(seconds: Double, sampleRate: Int): Int =
            (seconds * sampleRate * 2).toInt().coerceAtLeast(0)
    }
}
