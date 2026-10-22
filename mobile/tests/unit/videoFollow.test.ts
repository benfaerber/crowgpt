import { describe, expect, it } from "vitest";

import { followPicture, videoOffsetSec } from "../../src/domain/videoFollow";

/**
 * The picture follows the sound across the pre-roll offset.
 *
 * The desync these guard against read as a broken file: a 4-second clip
 * arriving with 19 seconds of audio, the caw heard fifteen seconds before the
 * crow appears. The offset is deliberate — the ring's seconds before the press
 * are usually the reason the capture exists — so playback has to carry it.
 */
describe("the picture follows the audio", () => {
  const base = {
    audioSec: 0,
    audioPlaying: true,
    audioJustPaused: false,
    offsetSec: 15,
    videoSec: 0,
    videoPlaying: false,
    videoDurationSec: 4,
  };

  it("waits on the first frame while the sound is still in the pre-roll", () => {
    const action = followPicture({ ...base, audioSec: 10 });
    expect(action.play).toBeUndefined();
    expect(action.seekTo).toBeUndefined();
  });

  it("rewinds a picture left mid-clip when the sound starts over", () => {
    const action = followPicture({ ...base, audioSec: 3, videoSec: 2.5 });
    expect(action.seekTo).toBe(0);
  });

  it("starts the picture the moment the sound reaches it", () => {
    const action = followPicture({ ...base, audioSec: 15.2 });
    expect(action.play).toBe(true);
  });

  it("lets a picture in step run free", () => {
    // Seeking every report would stutter; the players run at the same rate
    // and only real drift is corrected.
    const action = followPicture({
      ...base, audioSec: 17, videoSec: 2.1, videoPlaying: true,
    });
    expect(action.play).toBeUndefined();
    expect(action.seekTo).toBeUndefined();
  });

  it("yanks the picture back when it drifts", () => {
    const action = followPicture({
      ...base, audioSec: 17, videoSec: 3.0, videoPlaying: true,
    });
    expect(action.seekTo).toBe(2);
  });

  it("stops the picture at its last frame while the sound plays on", () => {
    // The camera finalized before the audio stopped; the clip is shorter.
    const action = followPicture({
      ...base, audioSec: 19.5, videoSec: 3.9, videoPlaying: true,
    });
    expect(action.play).toBe(false);
  });

  it("pauses the picture the moment the sound pauses", () => {
    const action = followPicture({
      ...base,
      audioSec: 17, videoSec: 2, videoPlaying: true,
      audioPlaying: false, audioJustPaused: true,
    });
    expect(action.play).toBe(false);
  });

  it("does not re-pause a picture played by hand while the sound stays paused", () => {
    // The audio player keeps reporting while paused — a scrub, a settling
    // seek — and the first version pounced on every report: press play on the
    // picture and it stopped a beat later. Only the transition may pause.
    const action = followPicture({
      ...base,
      audioSec: 17, videoSec: 2, videoPlaying: true,
      audioPlaying: false, audioJustPaused: false,
    });
    expect(action).toEqual({});
  });

  it("leaves a hand-scrubbed picture alone while the sound is paused", () => {
    // Manual control stays honest: with the audio paused and the picture
    // already still, there is nothing to contest.
    const action = followPicture({
      ...base, audioSec: 17, videoSec: 1, audioPlaying: false,
    });
    expect(action).toEqual({});
  });

  it("follows before the clip length is known", () => {
    // The player reports duration 0 until the file loads; only the past-the-
    // end rule needs it, so everything else must still work.
    const action = followPicture({ ...base, audioSec: 16, videoDurationSec: 0 });
    expect(action.play).toBe(true);
  });
});

describe("the offset between sound and picture", () => {
  it("is the measured pre-roll when the recorder stamped it", () => {
    expect(videoOffsetSec(12.4, 19, 4)).toBe(12.4);
  });

  it("falls back to the durations for captures made before the stamp", () => {
    // Both files ended at the same press of Stop, which is the one thing the
    // recording guarantees — so the difference of lengths is the offset.
    expect(videoOffsetSec(undefined, 19, 4)).toBe(15);
  });

  it("is zero while the clip length is still unknown", () => {
    expect(videoOffsetSec(undefined, 19, 0)).toBe(0);
  });

  it("never goes negative", () => {
    // A clip longer than its audio would mean the files did not end together;
    // an offset below zero would push seeks past the start.
    expect(videoOffsetSec(undefined, 4, 19)).toBe(0);
    expect(videoOffsetSec(-1, 19, 4)).toBe(0);
  });
});
