package expo.modules.rawaudio

import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile

/**
 * 16-bit PCM WAV sink.
 *
 * The RIFF and data chunk sizes aren't known until capture ends, so the header
 * goes down with zeroed lengths and both are patched on close.
 */
class WavFile(
    private val file: File,
    private val sampleRate: Int,
    private val channels: Int = 1,
) {
    private val bitsPerSample = 16
    private val out = BufferedOutputStream(FileOutputStream(file))

    var dataBytes = 0L
        private set

    init {
        out.write(header(dataLen = 0))
    }

    val frameBytes: Int get() = channels * bitsPerSample / 8

    val durationMs: Long
        get() = (dataBytes / frameBytes.toDouble() / sampleRate * 1000).toLong()

    fun write(buffer: ByteArray, length: Int) {
        out.write(buffer, 0, length)
        dataBytes += length
    }

    fun close() {
        out.flush()
        out.close()
        RandomAccessFile(file, "rw").use { raf ->
            raf.seek(4); raf.write(intLE((36 + dataBytes).toInt()))
            raf.seek(40); raf.write(intLE(dataBytes.toInt()))
        }
    }

    private fun header(dataLen: Int): ByteArray {
        val byteRate = sampleRate * frameBytes
        val header = ByteArray(44)
        "RIFF".toByteArray().copyInto(header, 0)
        writeIntLE(header, 4, 36 + dataLen)
        "WAVE".toByteArray().copyInto(header, 8)
        "fmt ".toByteArray().copyInto(header, 12)
        writeIntLE(header, 16, 16)                    // PCM fmt chunk size
        writeShortLE(header, 20, 1)                   // audio format = PCM
        writeShortLE(header, 22, channels)
        writeIntLE(header, 24, sampleRate)
        writeIntLE(header, 28, byteRate)
        writeShortLE(header, 32, frameBytes)          // block align
        writeShortLE(header, 34, bitsPerSample)
        "data".toByteArray().copyInto(header, 36)
        writeIntLE(header, 40, dataLen)
        return header
    }

    private fun writeIntLE(b: ByteArray, off: Int, v: Int) = intLE(v).copyInto(b, off)

    private fun writeShortLE(b: ByteArray, off: Int, v: Int) {
        b[off] = (v and 0xff).toByte(); b[off + 1] = ((v shr 8) and 0xff).toByte()
    }

    private fun intLE(v: Int) = byteArrayOf(
        (v and 0xff).toByte(), ((v shr 8) and 0xff).toByte(),
        ((v shr 16) and 0xff).toByte(), ((v shr 24) and 0xff).toByte(),
    )
}
