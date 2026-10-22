/**
 * Keeping the picture in step with the sound.
 *
 * A video capture is two files with different pasts: the WAV reaches back
 * through the rolling buffer — up to PRE_ROLL_SEC before Record was pressed —
 * while the camera starts at the press. Played from zero together, the caw is
 * heard long before it is seen, which reads as a broken file rather than a
 * design decision. The pre-roll is kept on purpose (the seconds before the
 * press are usually the reason the capture exists), so the honest fix is for
 * playback to respect the offset rather than for the audio to lose its past.
 *
 * The audio player leads and the picture follows. Nothing here touches a
 * player; this is the decision, held apart from expo-audio and expo-video so a
 * test can drive the sequences — the same shape as micState and MicrophoneSwap.
 */

/** How far the picture may drift from the sound before it is yanked back. */
export const DRIFT_SEC = 0.5;

const EPS = 0.05;

export interface PictureFollow {
  /** The audio playhead, in the audio's own timeline. */
  audioSec: number;
  audioPlaying: boolean;
  /**
   * True only on the report where the audio went from playing to not.
   *
   * The pause acts on this transition and never again: the audio player keeps
   * reporting while paused (a scrub, a settling seek), and a rule that pauses
   * on every such report re-pauses a picture the recordist has just chosen to
   * play by hand — pressing play and watching it stop a beat later.
   */
  audioJustPaused: boolean;
  /** Seconds of sound before the picture begins. */
  offsetSec: number;
  /** Where the video player is, in the video's own timeline. */
  videoSec: number;
  videoPlaying: boolean;
  /** 0 until the video player has loaded the file. */
  videoDurationSec: number;
}

export interface FollowAction {
  /** Move the video player here, in the video's timeline. */
  seekTo?: number;
  /** true → play, false → pause, undefined → leave it alone. */
  play?: boolean;
}

/**
 * What the video player should do about where the audio is now.
 *
 * Meant to run on each audio position report. Manual control stays honest by
 * transition, not by silence: the audio player reports even while paused, so
 * the only pause this issues is the one where the sound itself just stopped —
 * they stopped together, or the picture silently runs ahead of a sound that is
 * no longer there. Every later report while paused leaves the picture alone,
 * which is what lets it be scrubbed and played by hand.
 */
export function followPicture(state: PictureFollow): FollowAction {
  const target = state.audioSec - state.offsetSec;

  if (!state.audioPlaying) {
    return state.audioJustPaused && state.videoPlaying ? { play: false } : {};
  }

  // Still inside the pre-roll: the picture has not started yet. Parked on its
  // first frame rather than playing early — a picture that runs before its
  // moment is the desync this file exists to end.
  if (target < 0) {
    return {
      play: state.videoPlaying ? false : undefined,
      seekTo: state.videoSec > EPS ? 0 : undefined,
    };
  }

  // The sound has outlived the picture — the audio also runs to the press of
  // Stop, but the camera finalized first. Left on its last frame.
  if (state.videoDurationSec > 0 && target >= state.videoDurationSec - EPS) {
    return state.videoPlaying ? { play: false } : {};
  }

  return {
    play: state.videoPlaying ? undefined : true,
    seekTo: Math.abs(state.videoSec - target) > DRIFT_SEC ? target : undefined,
  };
}

/**
 * Seconds of sound before the picture begins, best answer available.
 *
 * `preRollSec` is the measured drain of the ring, written by the recorder —
 * the true offset. Captures made before it was stamped onto video captures
 * fall back to the difference of the two durations, which leans on the one
 * thing the recording guarantees: both files ended at the same press of Stop.
 */
export function videoOffsetSec(
  preRollSec: number | undefined,
  audioDurationSec: number | undefined,
  videoDurationSec: number,
): number {
  if (preRollSec !== undefined) return Math.max(0, preRollSec);
  if (!audioDurationSec || videoDurationSec <= 0) return 0;
  return Math.max(0, audioDurationSec - videoDurationSec);
}
