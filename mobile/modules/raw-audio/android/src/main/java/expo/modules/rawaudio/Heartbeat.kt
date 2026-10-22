package expo.modules.rawaudio

/**
 * What each heartbeat timer says, given what the recorder is doing.
 *
 * Two timers rather than one because the states run at different cadences on
 * purpose: "is the buffer still alive" is an all-walk question a minute apart,
 * "am I still recording" only matters for the length of a capture and wants
 * answering every few seconds. Each timer speaks only for its own state, so a
 * switched-off state is simply a timer never scheduled.
 *
 * Kept apart from the Handler that schedules them so the mapping lives on the
 * JVM: the failure this feature exists for — a session dying silently in a
 * pocket — is precisely a tick that must say *nothing*, and "nothing" is the
 * easiest answer to get wrong from a phone.
 */
internal object Heartbeat {
    /**
     * `recording` is asked as well as `listening` although isListening() is
     * already active && !recording: a caller passing raw flags must get the
     * same silence, because a tick saying "listening" mid-capture would be the
     * cue claiming a state the recorder is not in.
     */
    fun listeningTick(recording: Boolean, listening: Boolean): Cue? =
        if (listening && !recording) Cue.LISTENING else null

    fun recordingTick(recording: Boolean): Cue? =
        if (recording) Cue.RECORDING else null
}
