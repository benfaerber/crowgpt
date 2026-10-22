/**
 * Idle mode's trigger, with the audio and the clock taken out.
 *
 * The phone sits armed for the fire-escape hour and starts a capture when the
 * crow band gets loud. Every decision that matters here is a *timing* decision
 * — was this buffer hot, has the hold run out, is the hour over — and JS
 * timers pause with the screen, which is exactly the state an unattended phone
 * is in. So the machine that makes those decisions runs in Kotlin, fed by the
 * capture thread; this file is its mirror, kept transition-for-transition with
 * IdleTrigger.kt so drift between them is a failing test rather than a
 * field discovery. The UI also renders from this shape.
 *
 * The thresholds are not guesses. Experiment 0013 swept the burst gate and
 * found 12 dB over the recording's own noise floor separates crow bursts from
 * background where 6 dB does not, in the 800–4000 Hz band the calls live in —
 * the same numbers crowgpt's segmenter has used ever since. The floor is
 * measured, not configured, because a quiet evening and a windy one differ by
 * more than any constant survives.
 *
 * The machine never touches the recorder. It returns commands — emit a start,
 * emit a stop, say the session is over — and the caller carries them out. That
 * is what lets a JVM test and a vitest run drive it through an hour nobody
 * wants to stand through.
 */

export interface IdleConfig {
  /** How long the armed session lasts before it stands down on its own. */
  armSeconds: number;
  /** Silence, in seconds, that ends a capture. Well above the 1.5 s pauses
   *  inside a bout, so one bout is one capture rather than five. */
  holdSeconds: number;
  /** The longest a single auto capture may run. A stuck trigger — a car
   *  alarm, a party — must not spend the whole hour on one file. */
  maxCaptureSeconds: number;
  /** Auto captures allowed per armed session. The runaway guard: hitting it
   *  disarms, because twenty triggers in an hour means the threshold is wrong
   *  for tonight, not that the crows are having a concert. */
  maxCaptures: number;
  /** How far above the measured floor a buffer must sit to count as a call. */
  triggerDb: number;
  /** The absolute gate, in dBFS. On a dead-quiet evening the measured floor
   *  sits near the mic's self-noise, and floor-plus-twelve would then still
   *  be near-silence — a threshold no crow is needed to cross. A crow a few
   *  metres off measures ~-40 dBFS over half a second, so -55 leaves margin
   *  while staying out of reach of the room tone. */
  minDb: number;
}

export const IDLE_DEFAULTS: IdleConfig = {
  armSeconds: 60 * 60,
  holdSeconds: 25,
  maxCaptureSeconds: 10 * 60,
  maxCaptures: 20,
  triggerDb: 12,
  minDb: -55,
};

/** The bounds the settings boxes clamp to. Same shape as the heartbeat ones:
 *  clamping honours intent better than silently restoring the old value. */
export const IDLE_BOUNDS = {
  armMinutes: { min: 5, max: 240 },
  holdSeconds: { min: 5, max: 120 },
  maxCaptureMinutes: { min: 1, max: 30 },
  maxCaptures: { min: 1, max: 100 },
  triggerDb: { min: 6, max: 30 },
  minDb: { min: -80, max: -20 },
} as const;

export function clampIdle(
  value: string,
  bounds: { min: number; max: number },
  fallback: number,
): number {
  const parsed = Number.parseInt(value.trim(), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(bounds.max, Math.max(bounds.min, parsed));
}

/**
 * The settings keys joined to the machine's config shape — minutes become
 * seconds here, once, rather than at every call site.
 */
export function idleConfigFrom(settings: {
  idleArmMinutes: number;
  idleHoldSeconds: number;
  idleMaxCaptureMinutes: number;
  idleMaxCaptures: number;
  idleTriggerDb: number;
  idleMinDb: number;
}): IdleConfig {
  return {
    armSeconds: settings.idleArmMinutes * 60,
    holdSeconds: settings.idleHoldSeconds,
    maxCaptureSeconds: settings.idleMaxCaptureMinutes * 60,
    maxCaptures: settings.idleMaxCaptures,
    triggerDb: settings.idleTriggerDb,
    minDb: settings.idleMinDb,
  };
}

/**
 * Whether one half-second of band energy counts as a call.
 *
 * Strictly above, matching the segmenter it is borrowed from. The floor
 * arrives measured (a rolling low percentile of recent buffers) and the
 * absolute gate keeps a silent evening's floor from arming a hair trigger.
 */
export function isHot(bandDb: number, floorDb: number, config: IdleConfig): boolean {
  return bandDb > Math.max(floorDb + config.triggerDb, config.minDb);
}

export type IdlePhase =
  | "armed"
  | "triggered"
  | "recording"
  | "stopping"
  | "cooldown"
  | "suspended"
  | "disarmed";

export type DisarmReason = "expired" | "captureCap" | "sessionFailed" | "manual";

export type IdleCommand =
  | { kind: "emitStart" }
  | { kind: "emitStop" }
  | { kind: "disarmed"; reason: DisarmReason }
  | { kind: "notify"; state: "armed" | "recording" | "reverted" };

/**
 * How long an emitted command goes unanswered before it is said again.
 *
 * The trigger crosses the native→JS bridge and JS may be slow to wake. The
 * pre-roll makes the latency free — a start that lands five seconds late
 * still reaches fifteen seconds back — but a start that never lands at all
 * is a missed bird, so an unacknowledged emit is repeated rather than trusted.
 */
export const REEMIT_MS = 5_000;

/**
 * The pause after a capture before the trigger re-arms.
 *
 * The recording drained the pre-roll ring, and a trigger that fires into an
 * empty ring records a call with no approach on the front of it. Ten seconds
 * refills most of the ring and is far shorter than the gap between bouts.
 */
export const COOLDOWN_MS = 10_000;

/**
 * One armed session. Built armed; `disarmed` is terminal — the caller throws
 * the machine away and builds a new one next time the button is pressed.
 */
export class IdleMachine {
  private phase_: IdlePhase = "armed";
  private reason_: DisarmReason | null = null;
  private captures = 0;
  private readonly deadline: number;
  /** When the running capture began, for the length cap. */
  private recordStartedAt = 0;
  /** The last buffer that counted as a call, for the hold. */
  private lastHotAt = 0;
  private lastEmitAt = 0;
  private cooldownUntil = 0;
  /**
   * The hour ended while something was still in flight. A capture spanning
   * the deadline is never cut — its own hold or cap ends it — but the session
   * must not survive it either.
   */
  private disarmAtEnd = false;

  constructor(private readonly config: IdleConfig, now: number) {
    this.deadline = now + config.armSeconds * 1000;
  }

  phase(): IdlePhase {
    return this.phase_;
  }

  disarmReason(): DisarmReason | null {
    return this.reason_;
  }

  capturesMade(): number {
    return this.captures;
  }

  deadlineMs(): number {
    return this.deadline;
  }

  /** Half a second of band energy, against the floor measured alongside it. */
  buffer(bandDb: number, floorDb: number, now: number): IdleCommand[] {
    const expired = this.checkDeadline(now);
    if (expired.length > 0 || this.phase_ === "disarmed") return expired;

    const hot = isHot(bandDb, floorDb, this.config);
    switch (this.phase_) {
      case "armed":
        if (!hot) return [];
        this.phase_ = "triggered";
        this.lastHotAt = now;
        return this.emit(now, { kind: "emitStart" });
      case "triggered":
        // The start is out but the recording has not begun. Only a hot buffer
        // re-emits: a start repeated into silence would begin a capture of
        // nothing, five seconds after whatever tripped the first one ended.
        if (hot) this.lastHotAt = now;
        if (hot && now - this.lastEmitAt >= REEMIT_MS) {
          return this.emit(now, { kind: "emitStart" });
        }
        return [];
      case "recording": {
        if (hot) this.lastHotAt = now;
        const overLong = now - this.recordStartedAt >= this.config.maxCaptureSeconds * 1000;
        const heldSilence = now - this.lastHotAt >= this.config.holdSeconds * 1000;
        if (overLong || heldSilence) {
          this.phase_ = "stopping";
          return this.emit(now, { kind: "emitStop" });
        }
        return [];
      }
      case "stopping":
        // Any buffer re-emits here, unlike `triggered`: the stop is about a
        // recording that is demonstrably still running, whatever the level.
        if (now - this.lastEmitAt >= REEMIT_MS) {
          return this.emit(now, { kind: "emitStop" });
        }
        return [];
      case "cooldown":
        if (now < this.cooldownUntil) return [];
        this.phase_ = "armed";
        // Fall through by re-entry: this buffer may itself be the next call.
        return this.buffer(bandDb, floorDb, now);
      case "suspended":
        return [];
    }
    return [];
  }

  /**
   * A recording began. Claimed when this machine asked for one; anything else
   * is the recordist's own capture, which suspends the trigger — a deliberate
   * recording must never be ended by an algorithm's idea of silence.
   */
  recordingStarted(now: number): IdleCommand[] {
    if (this.phase_ === "disarmed") return [];
    if (this.phase_ === "triggered") {
      this.phase_ = "recording";
      this.recordStartedAt = now;
      // The hold counts from the recording, not from the buffer that tripped
      // it — otherwise a slow bridge eats into the silence budget.
      this.lastHotAt = now;
      return [{ kind: "notify", state: "recording" }];
    }
    this.phase_ = "suspended";
    return [];
  }

  recordingStopped(now: number): IdleCommand[] {
    if (this.phase_ === "disarmed") return [];
    const mine = this.phase_ === "recording" || this.phase_ === "stopping";
    if (mine) this.captures += 1;
    if (mine && this.captures >= this.config.maxCaptures) {
      return this.disarmNow("captureCap");
    }
    if (this.disarmAtEnd || now >= this.deadline) {
      return this.disarmNow(this.reason_ ?? "expired");
    }
    if (mine) {
      this.phase_ = "cooldown";
      this.cooldownUntil = now + COOLDOWN_MS;
    } else {
      this.phase_ = "armed";
    }
    return [{ kind: "notify", state: "armed" }];
  }

  /**
   * The microphone died under the session. There is nothing left to listen
   * through, so the session is over from any state — the recorder's own
   * failure path collects a partial capture if one was running.
   */
  sessionFailed(): IdleCommand[] {
    if (this.phase_ === "disarmed") return [];
    return this.disarmNow("sessionFailed");
  }

  /** The recordist pressed Disarm. An auto capture in flight is ended first
   *  and filed as usual — disarming must not discard a bird. */
  disarm(now: number): IdleCommand[] {
    if (this.phase_ === "disarmed") return [];
    this.reason_ = "manual";
    if (this.phase_ === "recording") {
      this.disarmAtEnd = true;
      this.phase_ = "stopping";
      return this.emit(now, { kind: "emitStop" });
    }
    if (this.phase_ === "stopping" || this.phase_ === "suspended") {
      this.disarmAtEnd = true;
      return [];
    }
    return this.disarmNow("manual");
  }

  /** The native fallback timer. Buffers drive the clock while the microphone
   *  is alive; this exists for the deadline landing in a silent stretch. */
  tick(now: number): IdleCommand[] {
    if (this.phase_ === "disarmed") return [];
    return this.checkDeadline(now);
  }

  private checkDeadline(now: number): IdleCommand[] {
    if (now < this.deadline || this.disarmAtEnd) return [];
    switch (this.phase_) {
      case "armed":
      case "cooldown":
      // Triggered but nothing recording yet: the emitted start may still be
      // crossing the bridge, but waiting for a recording that may never come
      // would hold the microphone all night. Disarming wins; a start that
      // lands afterwards is ignored as any foreign recording is.
      case "triggered":
        return this.disarmNow("expired");
      default:
        // A capture is running or ending. It finishes on its own terms; the
        // session ends with it.
        this.disarmAtEnd = true;
        this.reason_ = this.reason_ ?? "expired";
        return [];
    }
  }

  private disarmNow(reason: DisarmReason): IdleCommand[] {
    this.phase_ = "disarmed";
    this.reason_ = this.reason_ ?? reason;
    return [
      { kind: "disarmed", reason: this.reason_ },
      { kind: "notify", state: "reverted" },
    ];
  }

  private emit(now: number, command: IdleCommand): IdleCommand[] {
    this.lastEmitAt = now;
    return [command];
  }
}
