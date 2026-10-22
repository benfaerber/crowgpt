import { describe, expect, it } from "vitest";

import {
  clampIdle,
  COOLDOWN_MS,
  isHot,
  REEMIT_MS,
  IDLE_BOUNDS,
  IDLE_DEFAULTS,
  IdleMachine,
  type IdleCommand,
  type IdleConfig,
} from "../../src/domain/idle";

const T0 = 1_000_000;
const QUIET = -70;
const FLOOR = -75;
/** Comfortably over floor + 12 and over the -55 dBFS gate. */
const CAW = -40;

function config(overrides: Partial<IdleConfig> = {}): IdleConfig {
  return { ...IDLE_DEFAULTS, ...overrides };
}

function kinds(commands: IdleCommand[]): string[] {
  return commands.map((c) => c.kind);
}

/** Arm, trip the trigger, and answer it — the state most scenarios start in. */
function recordingMachine(cfg = config()): { machine: IdleMachine; now: number } {
  const machine = new IdleMachine(cfg, T0);
  machine.buffer(CAW, FLOOR, T0);
  machine.recordingStarted(T0 + 500);
  return { machine, now: T0 + 500 };
}

describe("isHot", () => {
  it("a buffer twelve dB over the measured floor is a call", () => {
    // A floor loud enough that the relative rule is the binding one — with a
    // quieter floor the absolute gate takes over, tested below.
    const noisy = -60;
    expect(isHot(noisy + 13, noisy, config())).toBe(true);
    expect(isHot(noisy + 12, noisy, config())).toBe(false);
    expect(isHot(noisy + 11, noisy, config())).toBe(false);
  });

  it("a silent evening's floor cannot arm a hair trigger", () => {
    // Floor at -90: floor + 12 = -78, but nothing under the absolute gate
    // counts, however far over the measured floor it sits.
    expect(isHot(-60, -90, config())).toBe(false);
    expect(isHot(-54, -90, config())).toBe(true);
  });
});

describe("IdleMachine trigger", () => {
  it("one hot buffer asks for a recording", () => {
    const machine = new IdleMachine(config(), T0);
    expect(machine.buffer(QUIET, FLOOR, T0)).toEqual([]);
    expect(kinds(machine.buffer(CAW, FLOOR, T0 + 500))).toEqual(["emitStart"]);
    expect(machine.phase()).toBe("triggered");
  });

  it("an unanswered start is repeated on a hot buffer, not into silence", () => {
    const machine = new IdleMachine(config(), T0);
    machine.buffer(CAW, FLOOR, T0);
    // Still hot inside the re-emit window: nothing, the first is in flight.
    expect(machine.buffer(CAW, FLOOR, T0 + 2_000)).toEqual([]);
    // Quiet after the window: still nothing — a start repeated into silence
    // would record an empty capture five seconds after the sound ended.
    expect(machine.buffer(QUIET, FLOOR, T0 + REEMIT_MS)).toEqual([]);
    // Hot after the window: said again.
    expect(kinds(machine.buffer(CAW, FLOOR, T0 + REEMIT_MS + 500))).toEqual(["emitStart"]);
  });
});

describe("IdleMachine while recording", () => {
  it("the pauses inside a bout do not split it", () => {
    const { machine, now } = recordingMachine();
    // Crows pause up to ~1.5 s between units; the hold is far above that.
    let t = now;
    for (let i = 0; i < 5; i += 1) {
      t += 1_500;
      expect(machine.buffer(QUIET, FLOOR, t)).toEqual([]);
      t += 500;
      expect(machine.buffer(CAW, FLOOR, t)).toEqual([]);
    }
    expect(machine.phase()).toBe("recording");
  });

  it("held silence ends the capture", () => {
    const { machine, now } = recordingMachine(config({ holdSeconds: 25 }));
    expect(machine.buffer(QUIET, FLOOR, now + 24_000)).toEqual([]);
    expect(kinds(machine.buffer(QUIET, FLOOR, now + 25_000))).toEqual(["emitStop"]);
    expect(machine.phase()).toBe("stopping");
  });

  it("a capture that will not end quietly is capped", () => {
    // A car alarm holds the trigger hot; the cap is what stops it spending
    // the whole hour on one file.
    const cfg = config({ maxCaptureSeconds: 600 });
    const { machine, now } = recordingMachine(cfg);
    expect(machine.buffer(CAW, FLOOR, now + 599_000)).toEqual([]);
    expect(kinds(machine.buffer(CAW, FLOOR, now + 600_000))).toEqual(["emitStop"]);
  });

  it("an unanswered stop is repeated whatever the level", () => {
    const { machine, now } = recordingMachine();
    machine.buffer(QUIET, FLOOR, now + 25_000);
    expect(machine.buffer(QUIET, FLOOR, now + 27_000)).toEqual([]);
    expect(kinds(machine.buffer(QUIET, FLOOR, now + 25_000 + REEMIT_MS))).toEqual([
      "emitStop",
    ]);
  });

  it("the hold counts from the recording, not the buffer that tripped it", () => {
    const cfg = config({ holdSeconds: 25 });
    const machine = new IdleMachine(cfg, T0);
    machine.buffer(CAW, FLOOR, T0);
    // The bridge was slow: the recording begins four seconds after the call.
    machine.recordingStarted(T0 + 4_000);
    // 24 s of silence after the *start* — inside the hold, so no stop yet.
    expect(machine.buffer(QUIET, FLOOR, T0 + 4_000 + 24_000)).toEqual([]);
    expect(kinds(machine.buffer(QUIET, FLOOR, T0 + 4_000 + 25_000))).toEqual(["emitStop"]);
  });
});

describe("IdleMachine between captures", () => {
  function stopped(cfg = config()): { machine: IdleMachine; now: number } {
    const { machine, now } = recordingMachine(cfg);
    machine.buffer(QUIET, FLOOR, now + 30_000);
    machine.recordingStopped(now + 31_000);
    return { machine, now: now + 31_000 };
  }

  it("the cooldown lets the ring refill before the next trigger", () => {
    const { machine, now } = stopped();
    expect(machine.phase()).toBe("cooldown");
    expect(machine.buffer(CAW, FLOOR, now + COOLDOWN_MS - 1_000)).toEqual([]);
    expect(kinds(machine.buffer(CAW, FLOOR, now + COOLDOWN_MS))).toEqual(["emitStart"]);
  });

  it("the capture cap disarms rather than carrying on", () => {
    const cfg = config({ maxCaptures: 2 });
    const { machine, now } = stopped(cfg);
    expect(machine.capturesMade()).toBe(1);
    // Second capture.
    let t = now + COOLDOWN_MS;
    machine.buffer(CAW, FLOOR, t);
    machine.recordingStarted(t + 500);
    machine.buffer(QUIET, FLOOR, t + 30_000);
    const commands = machine.recordingStopped(t + 31_000);
    expect(kinds(commands)).toEqual(["disarmed", "notify"]);
    expect(machine.disarmReason()).toBe("captureCap");
    expect(machine.phase()).toBe("disarmed");
  });
});

describe("IdleMachine and the recordist", () => {
  it("a recording the machine did not ask for suspends the trigger", () => {
    const machine = new IdleMachine(config(), T0);
    machine.recordingStarted(T0 + 1_000);
    expect(machine.phase()).toBe("suspended");
    // A deliberate capture is never ended by an algorithm's idea of silence.
    expect(machine.buffer(QUIET, FLOOR, T0 + 120_000)).toEqual([]);
    // And it does not count against the cap.
    machine.recordingStopped(T0 + 130_000);
    expect(machine.capturesMade()).toBe(0);
    expect(machine.phase()).toBe("armed");
  });

  it("disarming mid-capture files the bird before standing down", () => {
    const { machine, now } = recordingMachine();
    expect(kinds(machine.disarm(now + 5_000))).toEqual(["emitStop"]);
    const commands = machine.recordingStopped(now + 6_000);
    expect(kinds(commands)).toEqual(["disarmed", "notify"]);
    expect(machine.disarmReason()).toBe("manual");
  });

  it("disarming while armed is immediate", () => {
    const machine = new IdleMachine(config(), T0);
    expect(kinds(machine.disarm(T0 + 1_000))).toEqual(["disarmed", "notify"]);
    expect(machine.disarmReason()).toBe("manual");
  });
});

describe("IdleMachine and the hour", () => {
  it("the deadline stands the session down", () => {
    const cfg = config({ armSeconds: 3_600 });
    const machine = new IdleMachine(cfg, T0);
    expect(machine.tick(T0 + 3_599_000)).toEqual([]);
    const commands = machine.tick(T0 + 3_600_000);
    expect(kinds(commands)).toEqual(["disarmed", "notify"]);
    expect(machine.disarmReason()).toBe("expired");
  });

  it("a capture spanning the deadline finishes on its own terms", () => {
    const cfg = config({ armSeconds: 3_600, holdSeconds: 25 });
    const machine = new IdleMachine(cfg, T0);
    const late = T0 + 3_599_000;
    machine.buffer(CAW, FLOOR, late);
    machine.recordingStarted(late + 500);
    // The hour ends mid-capture: no cut.
    expect(machine.tick(T0 + 3_600_000)).toEqual([]);
    expect(machine.phase()).toBe("recording");
    // Its own hold ends it, and the session ends with it.
    expect(kinds(machine.buffer(QUIET, FLOOR, late + 500 + 25_000))).toEqual(["emitStop"]);
    const commands = machine.recordingStopped(late + 500 + 26_000);
    expect(kinds(commands)).toEqual(["disarmed", "notify"]);
    expect(machine.disarmReason()).toBe("expired");
  });

  it("a start still crossing the bridge at the deadline is abandoned", () => {
    const cfg = config({ armSeconds: 3_600 });
    const machine = new IdleMachine(cfg, T0);
    machine.buffer(CAW, FLOOR, T0 + 3_599_900);
    // Waiting for a recording that may never come would hold the microphone
    // all night; the session ends and a late start is treated as foreign.
    expect(kinds(machine.tick(T0 + 3_600_000))).toEqual(["disarmed", "notify"]);
  });
});

describe("IdleMachine when the microphone dies", () => {
  it("a dead session disarms from any state", () => {
    const { machine } = recordingMachine();
    const commands = machine.sessionFailed();
    expect(kinds(commands)).toEqual(["disarmed", "notify"]);
    expect(machine.disarmReason()).toBe("sessionFailed");
    // Terminal: nothing after this says anything.
    expect(machine.buffer(CAW, FLOOR, T0 + 60_000)).toEqual([]);
    expect(machine.sessionFailed()).toEqual([]);
  });
});

describe("clampIdle", () => {
  it("reads the box against its bounds", () => {
    expect(clampIdle("45", IDLE_BOUNDS.holdSeconds, 25)).toBe(45);
    expect(clampIdle("2", IDLE_BOUNDS.holdSeconds, 25)).toBe(5);
    expect(clampIdle("999", IDLE_BOUNDS.holdSeconds, 25)).toBe(120);
  });

  it("a box blurred mid-edit must not move the setting", () => {
    expect(clampIdle("", IDLE_BOUNDS.holdSeconds, 25)).toBe(25);
    expect(clampIdle("soon", IDLE_BOUNDS.holdSeconds, 25)).toBe(25);
  });
});
