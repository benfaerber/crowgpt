package expo.modules.rawaudio

/**
 * Tonight's noise floor, measured rather than configured.
 *
 * A quiet evening and a windy one differ by more than any constant survives,
 * so the trigger's threshold rides on the recording's own recent history: the
 * 20th percentile of the last two minutes of half-second band levels — the
 * same estimator crowgpt's segmenter validated, where 12 dB over this floor
 * separates crow bursts from background and 6 dB does not.
 *
 * The calls themselves are mostly kept out of it. The first field test found
 * the failure a plain ring hides: arm the trigger while calls are already
 * playing and the calls fill the window, the floor rides up toward them, and
 * "floor + 12" sits above the very sound it exists to catch — a threshold
 * chasing its own stimulus, the AGC failure in miniature. So the caller says
 * which buffers were hot, and only one in ten of those is let in: enough of a
 * leak that a street that gets *permanently* louder still raises the floor in
 * minutes, too little for a calling bout to raise it at all.
 *
 * Two minutes rather than the segmenter's whole-recording view because this
 * floor has to be trustworthy seconds after arming, not after a coffee.
 *
 * Not thread-safe; it lives on the capture thread with [BandEnergy].
 */
internal class NoiseFloor(private val capacity: Int = DEFAULT_CAPACITY) {

    private val ring = DoubleArray(capacity)
    private var writePos = 0
    private var filled = 0
    private var hotSeen = 0

    /** `hot` is the caller's own verdict on this buffer, from the floor as it
     *  stood before it — the chicken-and-egg resolves because an empty ring
     *  reads as the loudest possible floor, so nothing is hot until the first
     *  quiet has been measured. */
    fun record(bandDb: Double, hot: Boolean = false) {
        if (hot) {
            hotSeen += 1
            if (hotSeen % HOT_SAMPLE_EVERY != 0) return
        }
        ring[writePos] = bandDb
        writePos = (writePos + 1) % capacity
        if (filled < capacity) filled += 1
    }

    /**
     * The 20th percentile of what has been heard so far.
     *
     * Sorting a few hundred doubles twice a second is nothing next to the
     * filtering that produced them. Before anything has been recorded the
     * floor is the loudest possible answer, so the first buffers can never
     * trigger — an armed phone spends its first seconds measuring the evening
     * rather than mistaking it for a bird.
     */
    fun floorDb(): Double {
        if (filled == 0) return 0.0
        val sorted = ring.copyOfRange(0, filled).sortedArray()
        return sorted[(FLOOR_PERCENTILE * (filled - 1)).toInt()]
    }

    companion object {
        /** Two minutes of half-second buffers. */
        const val DEFAULT_CAPACITY = 240

        /** Matches FLOOR_PCTL in crowgpt's segmenter. */
        const val FLOOR_PERCENTILE = 0.20

        /** The leak: one hot buffer in ten still lands in the window. */
        const val HOT_SAMPLE_EVERY = 10
    }
}
