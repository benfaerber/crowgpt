import { describe, expect, it } from "vitest";

import type { Settings } from "../../src/domain/settings";
import { resolveSettings, stickyCaptureDefaults } from "../../src/domain/settings";

// A stand-in for defaultSettings, which stays in AppServices because it reads
// the device name and the environment. Typed as Settings, so a field added
// there without one here stops compiling.
const defaultSettings: Settings = {
  fieldServerUrl: "http://127.0.0.1:5100",
  enrollToken: "dev-enroll",
  contributorName: "",
  deviceLabel: "Pixel 8",
  claimCode: "",
  micPriority: [],
  preRoll: false,
  normalizePlayback: true,
  locationPrecision: "exact",
  censorCoords: true,
  fuzzMiles: 5,
  homeRegion: "",
  regionsBackfilled: false,
  backgroundListening: false,
  headsetTrigger: false,
  volumeShutter: false,
  heartbeatListening: false,
  heartbeatRecording: false,
  heartbeatListeningSeconds: 60,
  heartbeatRecordingSeconds: 10,
  captureLock: true,
  strictSync: true,
  mapShowTrees: false,
  mapShowScout: false,
  mapFamilyHalos: false,
  mapHiddenSpecies: [],
  idleMode: false,
  idleArmMinutes: 60,
  idleHoldSeconds: 25,
  idleMaxCaptureMinutes: 10,
  idleMaxCaptures: 20,
  idleTriggerDb: 12,
  idleMinDb: -55,
  lastObserverRole: "",
  lastDistanceBand: "",
};

/**
 * What survives a restart.
 *
 * The microphone choice is the one that matters most: it is set once, and every
 * recording afterwards depends on it silently. A corpus half-recorded through
 * the wrong microphone is the failure the whole pinning feature exists to
 * prevent, and it would start with a setting that quietly reverted.
 */
describe("stored settings", () => {
  it("keeps a chosen microphone across launches", () => {
    // The single `micInput` pin this used to assert on is gone — it was never
    // editable from any screen once the priority list arrived. The property it
    // was guarding is unchanged and now belongs to the list.
    const saved: Partial<Settings> = {
      micPriority: [{ preference: "type:11", label: "Rode VideoMic" }],
    };
    expect(resolveSettings(defaultSettings, saved).micPriority[0].preference)
      .toBe("type:11");
  });

  it("keeps an order that happens to match the default", () => {
    // A merge that dropped the stored value would look correct whenever the two
    // agree — right answer, wrong reason, and wrong the day the default moves.
    const saved: Partial<Settings> = {
      micPriority: [{ preference: "builtin", label: "Phone microphone" }],
    };
    expect(resolveSettings(defaultSettings, saved).micPriority).toHaveLength(1);
  });

  it("falls back to the default when nothing was ever saved", () => {
    expect(resolveSettings(defaultSettings, undefined).micPriority).toEqual([]);
  });

  it("gives a setting added since the last save its default", () => {
    // A phone that saved before strictSync existed must not end up with it
    // undefined, which would read as off.
    const old = { deviceLabel: "Pixel 8" } as Partial<Settings>;
    expect(resolveSettings(defaultSettings, old).strictSync).toBe(true);
  });

  it("keeps every other stored choice too", () => {
    const saved: Partial<Settings> = {
      deviceLabel: "Pixel 8",
      preRoll: true,
      normalizePlayback: false,
      strictSync: false,
    };
    const resolved = resolveSettings(defaultSettings, saved);
    expect(resolved).toMatchObject(saved);
  });

  it("keeps the microphone order across launches", () => {
    // The reason the list exists: arranging it the evening before is only
    // useful if it is still arranged in the morning.
    const saved: Partial<Settings> = {
      micPriority: [
        { preference: "type:22", label: "VideoMic Me-C" },
        { preference: "builtin", label: "Phone microphone" },
      ],
    };
    const resolved = resolveSettings(defaultSettings, saved);
    expect(resolved.micPriority.map((m) => m.preference)).toEqual(["type:22", "builtin"]);
  });

  it("remembers a microphone that is not currently attached", () => {
    // Stored as data, not derived from what is plugged in — otherwise the good
    // mic disappears from the list the moment you unplug it.
    const saved: Partial<Settings> = {
      micPriority: [{ preference: "type:22", label: "VideoMic Me-C",
                      lastSeen: "2026-07-20T10:00:00Z" }],
    };
    const [first] = resolveSettings(defaultSettings, saved).micPriority;
    expect(first.label).toBe("VideoMic Me-C");
    expect(first.lastSeen).toBe("2026-07-20T10:00:00Z");
  });

  it("leaves the headset button with other apps until asked", () => {
    // The trigger claims the play/pause button from everything else on the
    // phone, so a phone that saved settings before it existed — or never chose
    // it — must resolve to off. Defaulting on would take YouTube's button as a
    // side effect of an app update.
    const old = { deviceLabel: "Pixel 8" } as Partial<Settings>;
    expect(resolveSettings(defaultSettings, old).headsetTrigger).toBe(false);
    expect(
      resolveSettings(defaultSettings, { headsetTrigger: true }).headsetTrigger,
    ).toBe(true);
  });

  it("leaves the volume keys as volume keys until asked", () => {
    // The shutter claims volume-up inside the app, so a phone that saved
    // settings before it existed must resolve to off — an update that turned
    // the rocker into a record button would be a recording nobody meant.
    const old = { deviceLabel: "Pixel 8" } as Partial<Settings>;
    expect(resolveSettings(defaultSettings, old).volumeShutter).toBe(false);
    expect(
      resolveSettings(defaultSettings, { volumeShutter: true }).volumeShutter,
    ).toBe(true);
  });

  it("keeps idle mode off for a phone that saved before it existed", () => {
    // An unattended microphone that starts recordings on its own is the last
    // thing an app update should switch on.
    const old = { deviceLabel: "Pixel 8" } as Partial<Settings>;
    const resolved = resolveSettings(defaultSettings, old);
    expect(resolved.idleMode).toBe(false);
    expect(resolved.idleHoldSeconds).toBe(25);
    expect(resolved.idleTriggerDb).toBe(12);
  });

  it("remembers the last observer role and distance across launches", () => {
    // The whole point of the sticky default: chosen once in the evening, still
    // the pre-selection the next morning.
    const saved: Partial<Settings> = {
      lastObserverRole: "feeder",
      lastDistanceBand: "under_5m",
    };
    const resolved = resolveSettings(defaultSettings, saved);
    expect(resolved.lastObserverRole).toBe("feeder");
    expect(resolved.lastDistanceBand).toBe("under_5m");
  });

  it("gives a phone that saved before the sticky answers existed nothing remembered", () => {
    const old = { deviceLabel: "Pixel 8" } as Partial<Settings>;
    const resolved = resolveSettings(defaultSettings, old);
    expect(resolved.lastObserverRole).toBe("");
    expect(resolved.lastDistanceBand).toBe("");
  });

  it("survives a round trip through storage", () => {
    // Settings are persisted as JSON, so this is the actual path.
    const chosen: Settings = {
      ...defaultSettings,
      micPriority: [{ preference: "type:11", label: "Rode VideoMic" }],
      preRoll: true,
    };
    const reloaded = JSON.parse(JSON.stringify(chosen)) as Partial<Settings>;
    const back = resolveSettings(defaultSettings, reloaded);
    expect(back.micPriority[0].preference).toBe("type:11");
    expect(back.preRoll).toBe(true);
  });
});

/**
 * What a new capture starts out claiming.
 *
 * The line that matters is between "the last answer, carried forward" and "no
 * answer at all" — a capture must never sync an empty string where undefined
 * is the honest value, because "nobody said" is a different claim from every
 * real one.
 */
describe("sticky capture defaults", () => {
  it("carries the remembered answers onto a new capture", () => {
    const settings: Settings = {
      ...defaultSettings,
      lastObserverRole: "feeder",
      lastDistanceBand: "under_5m",
    };
    expect(stickyCaptureDefaults(settings)).toEqual({
      observerRole: "feeder",
      distanceBand: "under_5m",
    });
  });

  it("pre-fills nothing when nothing has been answered yet", () => {
    const { observerRole, distanceBand } = stickyCaptureDefaults(defaultSettings);
    expect(observerRole).toBeUndefined();
    expect(distanceBand).toBeUndefined();
  });

  it("keeps a cleared answer cleared", () => {
    // Choosing "Not said" writes "" to the memory, and the next capture must
    // start unanswered rather than resurrecting the answer before it.
    const settings: Settings = {
      ...defaultSettings,
      lastObserverRole: "",
      lastDistanceBand: "",
    };
    expect(stickyCaptureDefaults(settings).observerRole).toBeUndefined();
    expect(stickyCaptureDefaults(settings).distanceBand).toBeUndefined();
  });

  it("remembers each answer independently", () => {
    const settings: Settings = { ...defaultSettings, lastObserverRole: "stranger" };
    const defaults = stickyCaptureDefaults(settings);
    expect(defaults.observerRole).toBe("stranger");
    expect(defaults.distanceBand).toBeUndefined();
  });
});
