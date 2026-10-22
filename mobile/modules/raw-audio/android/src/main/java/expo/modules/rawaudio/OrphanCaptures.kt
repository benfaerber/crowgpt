package expo.modules.rawaudio

import java.io.File
import java.io.RandomAccessFile

/**
 * Recovers audio that outlived the process that was writing it.
 *
 * Measured on the Pixel 8, 2026-07-29: force-stopping the app mid-recording
 * loses the capture completely. The samples are on disk — everything but the
 * last buffered write — but [WavFile] only patches the RIFF and data lengths in
 * close(), and the capture row is only written when stop() returns. So what
 * survives is a WAV claiming to hold zero samples that nothing in the database
 * points at: present, playable in principle, and invisible.
 *
 * That is the worst failure this app can have. A lost label can be redone; a
 * lost call cannot, and this one was silent — the recordist sees a capture list
 * with nothing new in it and no reason given.
 *
 * So the header is rewritten from the file's actual length and the file is
 * handed back for the caller to enter in the database. Nothing is deleted and
 * nothing is guessed: a WAV is a header plus samples, and the length of the
 * file is the length of the samples.
 */
object OrphanCaptures {

    /**
     * What [WavRecorder] names a CAPTURE's file — see createTempFile there.
     *
     * Public because it is a contract rather than a detail: anything recorded
     * through this module that is not a field capture must be named something
     * else, or this sweep will claim it. A spoken note is the case that exists
     * today, and the recordist's own voice entering the corpus as bird audio is
     * the failure being prevented.
     */
    const val CAPTURE_PREFIX = "capture_"
    private const val PREFIX = CAPTURE_PREFIX
    private const val SUFFIX = ".wav"
    const val HEADER_BYTES = 44L

    /**
     * Marks a WAV as being written right now.
     *
     * The first version of this recovered any capture file the database did not
     * account for, which cost a working feature within the hour: deleting a
     * capture removes its row and leaves the WAV, so the next sweep read every
     * deletion as an abandoned recording and put it straight back. Delete
     * appeared not to work, and the list filled up.
     *
     * "Unreferenced" and "abandoned mid-write" are different facts and only the
     * recorder knows the second one. So it says so explicitly: this marker is
     * created beside the file when writing starts and removed when the file is
     * closed. A marker still present is a process that died holding the pen —
     * the only thing worth recovering.
     */
    const val WRITING_MARKER = ".writing"

    fun isCaptureFile(name: String): Boolean =
        name.startsWith(PREFIX) && name.endsWith(SUFFIX)

    fun markerFor(file: File): File = File(file.absolutePath + WRITING_MARKER)

    /**
     * Whether a file holds recoverable audio.
     *
     * A header and nothing else is not a recording — that is a capture killed
     * between opening the file and the first write, and entering it would put a
     * zero-second row in the list for no gain. One frame is the smallest thing
     * that is honestly audio.
     */
    fun holdsAudio(fileLength: Long): Boolean = fileLength > HEADER_BYTES

    /** Sample bytes in a file of this length. */
    fun dataBytes(fileLength: Long): Long = (fileLength - HEADER_BYTES).coerceAtLeast(0)

    fun durationMs(fileLength: Long, sampleRate: Int, frameBytes: Int): Long {
        if (sampleRate <= 0 || frameBytes <= 0) return 0
        return (dataBytes(fileLength) / frameBytes.toDouble() / sampleRate * 1000).toLong()
    }

    /**
     * Whether the header still says zero — i.e. nobody closed this file.
     *
     * Checked rather than assumed so a repair is idempotent: a recovered file
     * that somehow comes round again is left alone rather than rewritten.
     */
    fun needsRepair(declaredDataBytes: Long, fileLength: Long): Boolean =
        declaredDataBytes != dataBytes(fileLength)

    /**
     * Patch the RIFF and data lengths to match the file, and report the audio.
     * Returns null for files that hold no samples.
     */
    fun repair(file: File, sampleRate: Int, frameBytes: Int): Map<String, Any?>? {
        val length = file.length()
        if (!holdsAudio(length)) return null
        RandomAccessFile(file, "rw").use { raf ->
            raf.seek(40)
            val declared = readIntLE(raf).toLong()
            if (needsRepair(declared, length)) {
                raf.seek(4)
                writeIntLE(raf, (length - 8).toInt())
                raf.seek(40)
                writeIntLE(raf, dataBytes(length).toInt())
            }
        }
        return mapOf(
            "path" to file.absolutePath,
            "bytes" to length,
            "durationMs" to durationMs(length, sampleRate, frameBytes),
            "sampleRate" to sampleRate,
            // The clock is the only evidence of when this was recorded — the
            // capture row that would have said so was never written.
            "modifiedAt" to file.lastModified(),
        )
    }

    /**
     * Every capture a process died while writing.
     *
     * Both conditions are required and neither is sufficient. A [WRITING_MARKER]
     * says the recorder never closed this file; `known` excludes anything the
     * database already holds, which covers a live capture whose row is not
     * written yet. A file with no marker is not a candidate however unreferenced
     * it looks — that is a capture somebody deleted, and recovering it is how
     * this feature broke delete.
     *
     * The marker is cleared as each file is recovered, so a second sweep finds
     * nothing and a recovered capture the recordist then deletes stays deleted.
     */
    fun scan(
        dir: File,
        known: Set<String>,
        sampleRate: Int,
        frameBytes: Int,
    ): List<Map<String, Any?>> =
        (dir.listFiles() ?: emptyArray())
            .filter {
                it.isFile
                    && isCaptureFile(it.name)
                    && it.absolutePath !in known
                    && markerFor(it).exists()
            }
            // Oldest first, so a run that recovers several enters them in the
            // order they were recorded.
            .sortedBy { it.lastModified() }
            .mapNotNull { file ->
                repair(file, sampleRate, frameBytes).also { markerFor(file).delete() }
            }

    private fun readIntLE(raf: RandomAccessFile): Int {
        val b = ByteArray(4)
        raf.readFully(b)
        return (b[0].toInt() and 0xff) or ((b[1].toInt() and 0xff) shl 8) or
            ((b[2].toInt() and 0xff) shl 16) or ((b[3].toInt() and 0xff) shl 24)
    }

    private fun writeIntLE(raf: RandomAccessFile, v: Int) {
        raf.write(
            byteArrayOf(
                (v and 0xff).toByte(), ((v shr 8) and 0xff).toByte(),
                ((v shr 16) and 0xff).toByte(), ((v shr 24) and 0xff).toByte(),
            ),
        )
    }
}
