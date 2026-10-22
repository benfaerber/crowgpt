package expo.modules.rawaudio

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.log10
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * How loud one buffer is in the band crow calls live in, as dBFS.
 *
 * The broadband meter the app already has hands its triggers to traffic: most
 * of an urban evening's energy is rumble below 800 Hz, and a bus pulling away
 * would out-shout every caw. Crow fundamentals and their first harmonics sit
 * in 800–4000 Hz — the same band crowgpt's segmenter and the analyzer's SNR
 * measure — so the trigger listens there and nowhere else.
 *
 * Two cascaded biquads per edge (fourth-order Butterworth): ~24 dB per octave,
 * which puts a 100 Hz bus some 70 dB down and an 8 kHz brake squeal ~24 dB
 * down. Filter state carries across buffers because the stream is continuous;
 * one instance belongs to one microphone session.
 *
 * Not thread-safe; it runs on the capture thread that owns the buffers.
 */
internal class BandEnergy(sampleRate: Int) {

    private val sections = arrayOf(
        // Fourth-order Butterworth pairs: Q of 0.5412 and 1.3066 per edge.
        Biquad.highPass(HIGH_PASS_HZ, sampleRate, 0.5412),
        Biquad.highPass(HIGH_PASS_HZ, sampleRate, 1.3066),
        Biquad.lowPass(LOW_PASS_HZ, sampleRate, 0.5412),
        Biquad.lowPass(LOW_PASS_HZ, sampleRate, 1.3066),
    )

    /** Band RMS of one 16-bit little-endian mono buffer, in dBFS. */
    fun bandDbfs(bytes: ByteArray, length: Int): Double {
        var sum = 0.0
        var i = 0
        while (i + 1 < length) {
            val raw = (bytes[i].toInt() and 0xff) or (bytes[i + 1].toInt() shl 8)
            var sample = raw.toShort().toDouble() / 32768.0
            for (section in sections) sample = section.process(sample)
            sum += sample * sample
            i += 2
        }
        val n = (length / 2).coerceAtLeast(1)
        val rms = sqrt(sum / n)
        // The same floor AudioSourceProbe uses: digital silence is not
        // negative infinity, it is "quieter than anything we can act on".
        if (rms <= 0.0) return FLOOR_DB
        return (20.0 * log10(rms)).coerceAtLeast(FLOOR_DB)
    }

    /**
     * One direct-form-I biquad, coefficients from the RBJ audio-EQ cookbook —
     * the standard closed forms, kept exactly so the test's sine sweep is
     * checking our transcription rather than our numerics.
     */
    private class Biquad(
        private val b0: Double,
        private val b1: Double,
        private val b2: Double,
        private val a1: Double,
        private val a2: Double,
    ) {
        private var x1 = 0.0
        private var x2 = 0.0
        private var y1 = 0.0
        private var y2 = 0.0

        fun process(x: Double): Double {
            val y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2 = x1
            x1 = x
            y2 = y1
            y1 = y
            return y
        }

        companion object {
            fun lowPass(freq: Double, sampleRate: Int, q: Double): Biquad {
                val w0 = 2.0 * PI * freq / sampleRate
                val alpha = sin(w0) / (2.0 * q)
                val cosW0 = cos(w0)
                val a0 = 1.0 + alpha
                return Biquad(
                    b0 = (1.0 - cosW0) / 2.0 / a0,
                    b1 = (1.0 - cosW0) / a0,
                    b2 = (1.0 - cosW0) / 2.0 / a0,
                    a1 = -2.0 * cosW0 / a0,
                    a2 = (1.0 - alpha) / a0,
                )
            }

            fun highPass(freq: Double, sampleRate: Int, q: Double): Biquad {
                val w0 = 2.0 * PI * freq / sampleRate
                val alpha = sin(w0) / (2.0 * q)
                val cosW0 = cos(w0)
                val a0 = 1.0 + alpha
                return Biquad(
                    b0 = (1.0 + cosW0) / 2.0 / a0,
                    b1 = -(1.0 + cosW0) / a0,
                    b2 = (1.0 + cosW0) / 2.0 / a0,
                    a1 = -2.0 * cosW0 / a0,
                    a2 = (1.0 - alpha) / a0,
                )
            }
        }
    }

    companion object {
        /** The crow band, matching crowgpt's segmenter and analyzer/quality.py. */
        const val HIGH_PASS_HZ = 800.0
        const val LOW_PASS_HZ = 4000.0
        const val FLOOR_DB = -120.0
    }
}
