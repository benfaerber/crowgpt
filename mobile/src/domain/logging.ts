/**
 * What the app says about itself.
 *
 * The field app is debugged by whoever is holding it, standing in a park, with
 * no cable. `adb logcat` is only true while USB is attached, and it is wiped by
 * the reinstall that follows every fix — which is how a NullPointerException on
 * the Pixel 10 was lost twice in one afternoon while being actively chased.
 *
 * So the phone keeps its own log, on the phone, and pushes it when asked. Three
 * rules follow from that and every design decision below is one of them:
 *
 *   1. Logging must never throw. A logger that can fail turns one bug into two,
 *      and the second one lands in whatever code was reporting the first.
 *   2. Logging must never block. The recorder calls it, and nothing in the
 *      recorder's path may wait on a database write.
 *   3. It must work before the database does. The failures worth catching
 *      include "the database would not open", which is precisely when a
 *      SQLite-backed logger has nothing to write to.
 *
 * Rule 3 is why there is a ring buffer here at all: entries are accepted from
 * process start into memory, and drain into storage once storage exists. If it
 * never does, they are still readable on screen, which is the whole point.
 */

export type LogLevel = "debug" | "info" | "warn" | "error";

/** Worst last, so a filter can say "this and above" by slicing. */
export const LEVELS: readonly LogLevel[] = ["debug", "info", "warn", "error"];

export interface LogEntry {
  /** Idempotency key — the server dedupes on it, so a resend is free. */
  uuid: string;
  /** The phone's clock. Kept even when it disagrees with the server's. */
  at: string;
  level: LogLevel;
  /** Which part of the app spoke: recorder, sync, db, app, ui. */
  tag: string;
  message: string;
  /** Anything structured worth having: ids, sizes, status codes, stacks. */
  detail?: unknown;
}

export interface StoredLogEntry extends LogEntry {
  /** Set once the server has confirmed it. */
  syncedAt?: string;
}

/** Matches the server's clip, so a line reads the same in both places. */
export const MAX_MESSAGE = 4000;

export function clip(text: string, limit = MAX_MESSAGE): string {
  return text.length <= limit ? text : `${text.slice(0, limit)}…`;
}

/**
 * Turn whatever was thrown into something worth reading a week later.
 *
 * Errors arrive here as anything at all — an Error, a string, a native
 * rejection object with a `code`, occasionally `undefined`. `String(error)` on
 * the last two produces "undefined" and "[object Object]", which is how a
 * logged failure becomes indistinguishable from no failure.
 */
export function describeError(error: unknown): { message: string; detail?: unknown } {
  if (error instanceof Error) {
    return {
      message: `${error.name}: ${error.message}`,
      detail: {
        stack: error.stack,
        // Native module rejections carry a code and nothing else useful.
        code: (error as { code?: unknown }).code,
      },
    };
  }
  if (error && typeof error === "object") {
    try {
      return { message: JSON.stringify(error), detail: error };
    } catch {
      return { message: Object.prototype.toString.call(error) };
    }
  }
  return { message: String(error) };
}

/**
 * The last N entries, oldest evicted first.
 *
 * Bounded because a crash loop writes the same line thousands of times a
 * minute, and the newest are the ones that describe what is happening now.
 */
export class LogRing {
  private entries: LogEntry[] = [];

  constructor(private readonly capacity = 500) {}

  add(entry: LogEntry): void {
    this.entries.push(entry);
    if (this.entries.length > this.capacity) {
      this.entries.splice(0, this.entries.length - this.capacity);
    }
  }

  /** Everything held, oldest first. */
  all(): LogEntry[] {
    return [...this.entries];
  }

  /** Hand everything over and forget it — used when storage becomes available. */
  drain(): LogEntry[] {
    const held = this.entries;
    this.entries = [];
    return held;
  }

  get size(): number {
    return this.entries.length;
  }
}
