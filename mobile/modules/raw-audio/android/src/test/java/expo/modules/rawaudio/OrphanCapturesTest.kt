package expo.modules.rawaudio

import java.io.File
import java.io.RandomAccessFile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/**
 * Recovering a recording whose process was killed.
 *
 * Driven through real files rather than mocks, because the thing being tested
 * is what is actually on disk after a SIGKILL: 44 bytes of header claiming
 * zero samples, followed by however many samples had been flushed.
 */
class OrphanCapturesTest {

    @get:Rule
    val folder = TemporaryFolder()

    /** The marker the recorder leaves beside a file it is still writing. */
    private fun markWriting(file: File) {
        OrphanCaptures.markerFor(file).createNewFile()
    }

    /** A file exactly as a killed process leaves it: real samples, header says 0. */
    private fun abandonedCapture(name: String, sampleBytes: Int): File {
        val file = folder.newFile(name)
        val wav = WavFile(file, sampleRate = 48000)
        wav.write(ByteArray(sampleBytes), sampleBytes)
        // Deliberately no close(): that is the whole scenario. Flush by hand so
        // the bytes reach disk, which is what the OS does for a dying process's
        // already-written pages.
        RandomAccessFile(file, "rw").use { }
        return file
    }

    @Test
    fun `a killed capture is found and its header repaired`() {
        val file = folder.newFile("capture_1.wav")
        // Write the shape by hand: header with zeroed lengths, then samples.
        RandomAccessFile(file, "rw").use { raf ->
            raf.write(ByteArray(44))
            raf.write(ByteArray(96000))
        }
        markWriting(file)
        val found = OrphanCaptures.scan(folder.root, emptySet(), 48000, frameBytes = 2)

        assertEquals(1, found.size)
        assertEquals(file.absolutePath, found[0]["path"])
        assertEquals(96044L, found[0]["bytes"])
        // 96000 bytes / 2 per frame / 48000 Hz = 1 second.
        assertEquals(1000L, found[0]["durationMs"])
    }

    @Test
    fun `the repaired header states the real sample count`() {
        val file = folder.newFile("capture_2.wav")
        RandomAccessFile(file, "rw").use { raf ->
            raf.write(ByteArray(44))
            raf.write(ByteArray(2048))
        }
        OrphanCaptures.repair(file, 48000, frameBytes = 2)

        RandomAccessFile(file, "r").use { raf ->
            raf.seek(4)
            assertEquals("RIFF size is everything after the first 8 bytes", 2084, readIntLE(raf))
            raf.seek(40)
            assertEquals("data size is the samples", 2048, readIntLE(raf))
        }
    }

    @Test
    fun `a capture the database already holds is left alone`() {
        // The ordinary case, and the one that must never produce a duplicate:
        // every healthy capture's file is sitting in this directory too.
        val file = folder.newFile("capture_3.wav")
        RandomAccessFile(file, "rw").use { raf -> raf.write(ByteArray(4144)) }
        markWriting(file)

        val found = OrphanCaptures.scan(
            folder.root, setOf(file.absolutePath), 48000, frameBytes = 2,
        )
        assertTrue(found.isEmpty())
    }

    @Test
    fun `a header with no samples is not a recording`() {
        // Killed between opening the file and the first write. Entering it would
        // put a zero-second capture in the list and call that a rescue.
        val file = folder.newFile("capture_4.wav")
        RandomAccessFile(file, "rw").use { raf -> raf.write(ByteArray(44)) }
        markWriting(file)

        assertNull(OrphanCaptures.repair(file, 48000, frameBytes = 2))
        assertTrue(OrphanCaptures.scan(folder.root, emptySet(), 48000, 2).isEmpty())
    }

    @Test
    fun `only this recorder's files are touched`() {
        folder.newFile("probe_builtin.wav")
        folder.newFile("something.mp4")
        folder.newFile("capture_5.wav").also { f ->
            RandomAccessFile(f, "rw").use { it.write(ByteArray(1044)) }
            markWriting(f)
        }

        val found = OrphanCaptures.scan(folder.root, emptySet(), 48000, frameBytes = 2)
        assertEquals(1, found.size)
        assertTrue((found[0]["path"] as String).endsWith("capture_5.wav"))
        assertFalse(OrphanCaptures.isCaptureFile("probe_builtin.wav"))
    }

    @Test
    fun `a spoken note the app died during is never claimed as a capture`() {
        // The whole reason RecordingOptions carries a prefix. A dictation lands
        // in the same cache directory and leaves the same .writing marker, so
        // without a different name this sweep would enter the recordist's own
        // voice into the corpus as field audio at the next launch — the
        // contamination the Keep flag exists to hold back, arriving by a route
        // nobody would think to check.
        folder.newFile("dictation_9.wav").also { f ->
            RandomAccessFile(f, "rw").use { it.write(ByteArray(96_044)) }
            markWriting(f)
        }
        folder.newFile("capture_9.wav").also { f ->
            RandomAccessFile(f, "rw").use { it.write(ByteArray(96_044)) }
            markWriting(f)
        }

        val found = OrphanCaptures.scan(folder.root, emptySet(), 48000, frameBytes = 2)

        assertEquals(1, found.size)
        assertTrue((found[0]["path"] as String).endsWith("capture_9.wav"))
        assertFalse(OrphanCaptures.isCaptureFile("dictation_9.wav"))
    }

    @Test
    fun `repairing twice changes nothing the second time`() {
        val file = folder.newFile("capture_6.wav")
        RandomAccessFile(file, "rw").use { raf -> raf.write(ByteArray(5044)) }

        val once = OrphanCaptures.repair(file, 48000, frameBytes = 2)
        val twice = OrphanCaptures.repair(file, 48000, frameBytes = 2)
        assertEquals(once?.get("bytes"), twice?.get("bytes"))
        assertEquals(once?.get("durationMs"), twice?.get("durationMs"))
        assertFalse(OrphanCaptures.needsRepair(5000, 5044))
    }

    @Test
    fun `several orphans come back oldest first`() {
        // So a phone that died twice enters them in the order they happened.
        val older = folder.newFile("capture_7.wav")
        val newer = folder.newFile("capture_8.wav")
        RandomAccessFile(older, "rw").use { it.write(ByteArray(1044)) }
        RandomAccessFile(newer, "rw").use { it.write(ByteArray(1044)) }
        markWriting(older)
        markWriting(newer)
        older.setLastModified(1_000_000)
        newer.setLastModified(2_000_000)

        val found = OrphanCaptures.scan(folder.root, emptySet(), 48000, frameBytes = 2)
        assertEquals(
            listOf(older.absolutePath, newer.absolutePath),
            found.map { it["path"] },
        )
    }

    @Test
    fun `a real WavFile that was never closed is recoverable`() {
        // The actual failure path end to end: WavFile wrote the header and the
        // samples, and close() — which patches the lengths — never ran.
        val file = abandonedCapture("capture_9.wav", sampleBytes = 48000)
        markWriting(file)
        RandomAccessFile(file, "r").use { raf ->
            raf.seek(40)
            assertEquals("the abandoned header claims nothing", 0, readIntLE(raf))
        }

        val recovered = OrphanCaptures.repair(file, 48000, frameBytes = 2)
        assertEquals(500L, recovered?.get("durationMs"))
    }

    @Test
    fun `a deleted capture is never brought back`() {
        // THE REGRESSION. Deleting a capture removes its row and leaves the WAV,
        // so the first version of this — recover anything the database does not
        // account for — read every deletion as an abandoned recording and put it
        // straight back. Delete looked broken and the list filled up. No marker
        // means the recorder closed this file properly; whatever happened to it
        // afterwards was somebody's decision.
        val file = folder.newFile("capture_deleted.wav")
        RandomAccessFile(file, "rw").use { raf ->
            raf.write(ByteArray(44))
            raf.write(ByteArray(96000))
        }

        assertTrue(
            "a closed file is not an abandoned one",
            OrphanCaptures.scan(folder.root, emptySet(), 48000, frameBytes = 2).isEmpty(),
        )
    }

    @Test
    fun `recovering clears the marker, so the capture can then be deleted for good`() {
        // Otherwise the marker outlives the recovery and the next sweep offers
        // the same file again — the same resurrection, one launch later.
        val file = folder.newFile("capture_once.wav")
        RandomAccessFile(file, "rw").use { raf -> raf.write(ByteArray(48044)) }
        markWriting(file)

        assertEquals(1, OrphanCaptures.scan(folder.root, emptySet(), 48000, 2).size)
        assertFalse(OrphanCaptures.markerFor(file).exists())
        assertTrue(OrphanCaptures.scan(folder.root, emptySet(), 48000, 2).isEmpty())
    }

    private fun readIntLE(raf: RandomAccessFile): Int {
        val b = ByteArray(4)
        raf.readFully(b)
        return (b[0].toInt() and 0xff) or ((b[1].toInt() and 0xff) shl 8) or
            ((b[2].toInt() and 0xff) shl 16) or ((b[3].toInt() and 0xff) shl 24)
    }
}
