package expo.modules.rawaudio

import kotlin.math.PI
import kotlin.math.sin
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The band filter checked with sines, because the whole trigger rides on it:
 * a filter transcribed wrong would either hand triggers back to the traffic
 * rumble it exists to remove, or file the crows under it.
 */
class BandEnergyTest {

    private val sampleRate = 48_000

    /** Half a second of 16-bit mono sine, amplitude 0.5 of full scale. */
    private fun sineBuffer(freqHz: Double, phaseOffset: Int): ByteArray {
        val samples = sampleRate / 2
        val bytes = ByteArray(samples * 2)
        for (i in 0 until samples) {
            val t = (phaseOffset + i).toDouble() / sampleRate
            val value = (0.5 * sin(2.0 * PI * freqHz * t) * 32767.0).toInt()
            bytes[i * 2] = (value and 0xff).toByte()
            bytes[i * 2 + 1] = ((value shr 8) and 0xff).toByte()
        }
        return bytes
    }

    /** Feed a settling buffer first, then measure the second — the filter
     *  state carries across buffers just as it does on the capture thread. */
    private fun measure(freqHz: Double): Double {
        val band = BandEnergy(sampleRate)
        val first = sineBuffer(freqHz, 0)
        band.bandDbfs(first, first.size)
        val second = sineBuffer(freqHz, sampleRate / 2)
        return band.bandDbfs(second, second.size)
    }

    @Test
    fun `a mid-band tone passes at its true level`() {
        // 0.5 amplitude sine: RMS 0.5/sqrt(2) = -9.0 dBFS.
        val db = measure(1_500.0)
        assertEquals(-9.0, db, 1.5)
    }

    @Test
    fun `traffic rumble is far below the trigger's reach`() {
        // 100 Hz is three octaves under the 800 Hz edge; fourth-order
        // Butterworth puts it ~70 dB down — no bus out-shouts a caw here.
        val inBand = measure(1_500.0)
        val rumble = measure(100.0)
        assertTrue("expected >= 40 dB of rejection, got ${inBand - rumble}", inBand - rumble >= 40.0)
    }

    @Test
    fun `high squeals are attenuated too`() {
        // 8 kHz is one octave over the 4 kHz edge: ~24 dB down.
        val inBand = measure(1_500.0)
        val squeal = measure(8_000.0)
        assertTrue("expected >= 20 dB of rejection, got ${inBand - squeal}", inBand - squeal >= 20.0)
    }

    @Test
    fun `digital silence reads as the floor, not negative infinity`() {
        val band = BandEnergy(sampleRate)
        val silence = ByteArray(sampleRate)
        assertEquals(BandEnergy.FLOOR_DB, band.bandDbfs(silence, silence.size), 0.0)
    }
}
