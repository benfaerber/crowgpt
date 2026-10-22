package expo.modules.rawaudio

import expo.modules.kotlin.records.Field
import expo.modules.kotlin.records.Record

class RecordingOptions : Record {
    @Field
    var sampleRate: Int = 48000

    /**
     * Which microphone to record through: "builtin" (default), "auto", or
     * "type:<n>" for a specific attached input. See [AudioInputs].
     */
    @Field
    var input: String = AudioInputs.BUILT_IN

    /**
     * What to name the file, so a recording that is NOT a capture cannot be
     * mistaken for one.
     *
     * A spoken note lands in the same cache directory as a capture, and a
     * process killed while writing one leaves the same `.writing` marker. Left
     * to the default prefix, [OrphanCaptures.scan] would sweep it up at the
     * next launch and enter the recordist's own voice into the corpus as field
     * audio. Naming it differently makes that impossible rather than merely
     * unlikely — see [OrphanCaptures.isCaptureFile].
     */
    @Field
    var prefix: String = "capture_"
}

class ListeningOptions : Record {
    @Field
    var sampleRate: Int = 48000

    @Field
    var input: String = AudioInputs.BUILT_IN

    /** Seconds of audio held in memory, available to the next recording. */
    @Field
    var preRollSeconds: Double = 15.0

    /**
     * Keep listening when the app is not on screen.
     *
     * Separate from the buffer itself because the costs are not comparable.
     * Holding the ring while somebody is watching the capture screen is nearly
     * free; holding it from a pocket needs a foreground service, an
     * undismissable notification and the battery to run the microphone all day.
     * One is a convenience, the other is a decision.
     */
    @Field
    var background: Boolean = false
}

class HeartbeatOptions : Record {
    /**
     * Between listening ticks. Zero or below means that heartbeat is off —
     * the interval carries the switch, so there is no flag to disagree with.
     */
    @Field
    var listeningSeconds: Double = 0.0

    /** Between recording beeps, on its own cadence. Zero or below is off. */
    @Field
    var recordingSeconds: Double = 0.0
}

/** Mirrors IdleConfig in mobile/src/domain/idle.ts, where every number
 *  is explained. Values arrive clamped by the settings screen. */
class IdleOptions : Record {
    @Field
    var armSeconds: Int = 3600

    @Field
    var holdSeconds: Int = 25

    @Field
    var maxCaptureSeconds: Int = 600

    @Field
    var maxCaptures: Int = 20

    @Field
    var triggerDb: Double = 12.0

    @Field
    var minDb: Double = -55.0

    /**
     * Whether standing down should also close the microphone and the service.
     *
     * Set by JS from whether listening was already running when Arm was
     * pressed: a buffer somebody had open for its own sake survives the
     * session, one opened *for* the session must not outlive it — an armed
     * hour that quietly became an armed night is the microphone held with
     * nobody meaning it.
     */
    @Field
    var stopListeningOnDisarm: Boolean = false

    /**
     * The deadline as words for the notification — "until 8:03 PM". Rendered
     * in JS, which owns locale and wall clocks; the native side deliberately
     * measures time in elapsedRealtime and has no business formatting one.
     */
    @Field
    var untilLabel: String = ""
}

class ProbeOptions : Record {
    @Field
    var sampleRate: Int = 48000

    @Field
    var millisPerSource: Int = 1500

    @Field
    var keepAudio: Boolean = true
}
