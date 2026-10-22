import { newClientUuid } from "../domain/ids";
import {
  LogRing,
  clip,
  describeError,
  type LogEntry,
  type LogLevel,
} from "../domain/logging";
import type { LogRepository } from "../data/LogRepository";
import type { RandomBytes } from "../domain/ids";

/**
 * How many entries may wait in memory before storage exists, and how many may
 * queue between flushes. Beyond it the oldest go — see LogRing.
 */
const RING = 500;

/**
 * Writes are batched on a short timer so that a caller never waits on SQLite.
 * Short enough that a crash a moment later still finds the line on disk, long
 * enough that a burst is one transaction rather than fifty.
 */
const FLUSH_MS = 400;

/**
 * The app's log.
 *
 * A module-level singleton, which is a deliberate exception to the composition
 * root everything else here goes through. Two reasons, both about the failures
 * it exists to catch: it has to be callable from the global error handler,
 * which runs with no services in scope, and from `AppServices.create` itself,
 * which is where "the database would not open" is thrown. A logger injected
 * through the thing that failed to build cannot report that it failed to build.
 *
 * Everything it does is safe when nothing is attached. Entries land in the ring
 * and drain into storage the moment there is any.
 */
export class Log {
  private repository?: LogRepository;
  private readonly ring = new LogRing(RING);
  private pending: LogEntry[] = [];
  private timer: ReturnType<typeof setTimeout> | undefined;
  private randomBytes?: RandomBytes;
  private sequence = 0;
  /** Guards against a log line written by the logging path itself. */
  private reentrant = false;

  /**
   * Start storing. Everything buffered since launch goes down with it, which is
   * the point — those are the entries from before the database existed.
   */
  attach(repository: LogRepository, randomBytes?: RandomBytes): void {
    this.repository = repository;
    if (randomBytes) this.randomBytes = randomBytes;
    this.pending.push(...this.ring.drain());
    this.schedule();
  }

  /** Available before `attach`, for the entries written before the store opened. */
  useRandomBytes(randomBytes: RandomBytes): void {
    this.randomBytes = randomBytes;
  }

  debug(tag: string, message: string, detail?: unknown): void {
    this.write("debug", tag, message, detail);
  }

  info(tag: string, message: string, detail?: unknown): void {
    this.write("info", tag, message, detail);
  }

  warn(tag: string, message: string, detail?: unknown): void {
    this.write("warn", tag, message, detail);
  }

  /**
   * Something that failed. Takes the thrown value rather than a string, because
   * the stack is the part worth having and `String(error)` throws it away.
   */
  error(tag: string, message: string, thrown?: unknown, detail?: unknown): void {
    const described = thrown === undefined ? undefined : describeError(thrown);
    this.write(
      "error",
      tag,
      described ? `${message} — ${described.message}` : message,
      described || detail
        ? { ...(described?.detail as object | undefined), ...(detail as object | undefined) }
        : undefined,
    );
  }

  /** What is held but not yet written — for the diagnostics screen. */
  get buffered(): number {
    return this.ring.size + this.pending.length;
  }

  /** Everything still in memory, for when there is no database to read from. */
  inMemory(): LogEntry[] {
    return [...this.ring.all(), ...this.pending];
  }

  /**
   * A console call, flattened.
   *
   * The first Error among the arguments keeps its stack; the rest become the
   * message. Console calls carry the interesting part in different positions
   * depending on who wrote them, and `args.join(" ")` turns a stack trace into
   * "[object Object]".
   */
  fromConsole(level: "warn" | "error", args: unknown[]): void {
    const thrown = args.find((arg) => arg instanceof Error);
    const text = args
      .filter((arg) => arg !== thrown)
      .map((arg) => (typeof arg === "string" ? arg : safeText(arg)))
      .join(" ");
    if (level === "error") this.error("console", text || "error", thrown);
    else this.write("warn", "console", text || "warning",
                    thrown ? describeError(thrown).detail : undefined);
  }

  /** Force the queue down now — before a sync, or when a screen wants to read. */
  async flush(): Promise<void> {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = undefined;
    }
    // Anything the ring is holding goes first: those are either from before
    // the store existed, or from a write that failed. Without this they are
    // held forever — flush only ever looked at the queue, so a store that came
    // back never got the entries it had rejected, which is precisely the run of
    // entries somebody would be looking for.
    const batch = [...this.ring.drain(), ...this.pending];
    this.pending = [];
    if (batch.length === 0 || !this.repository) {
      // Nowhere to put them: back into the ring rather than dropped, so they
      // survive until there is.
      for (const entry of batch) this.ring.add(entry);
      return;
    }
    try {
      await this.repository.append(batch);
    } catch {
      // The store rejected the write. Keeping them in memory is all that is
      // left, and it is better than the alternative — this is exactly the
      // failure the log is for, and it must not be reported by throwing from
      // inside whatever was already going wrong.
      for (const entry of batch) this.ring.add(entry);
    }
  }

  write(level: LogLevel, tag: string, message: string, detail?: unknown): void {
    if (this.reentrant) return;
    this.reentrant = true;
    try {
      this.pending.push({
        uuid: this.nextUuid(),
        at: new Date().toISOString(),
        level,
        tag,
        message: clip(message),
        detail,
      });
      if (this.pending.length > RING) this.pending.splice(0, this.pending.length - RING);
      // Errors and warnings go down immediately rather than waiting out the
      // batch timer. The entries worth having are exactly the ones written
      // shortly before something goes badly enough wrong that there is no next
      // tick — a freeze, a kill, a reboot by a person who has had enough.
      if (level === "error" || level === "warn") void this.flush();
      else this.schedule();
    } catch {
      // Nothing to do that would not itself be logging.
    } finally {
      this.reentrant = false;
    }
  }

  private schedule(): void {
    if (this.timer || !this.repository) return;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      void this.flush();
    }, FLUSH_MS);
  }

  /**
   * An id that does not depend on anything that can fail.
   *
   * Hermes has no `crypto` global, and `expo-crypto` is a native module — which
   * may be exactly what is broken when something is being logged. So the real
   * source is used when it is there, and a counter is used when it is not.
   * These are idempotency keys, not secrets; uniqueness on one device is the
   * only requirement.
   */
  private nextUuid(): string {
    this.sequence += 1;
    if (this.randomBytes) {
      try {
        return newClientUuid(this.randomBytes);
      } catch {
        this.randomBytes = undefined;
      }
    }
    return `local-${Date.now().toString(36)}-${this.sequence.toString(36)}`;
  }
}

/** The one the app uses. */
export const log = new Log();

/**
 * Route uncaught errors and console noise into the log.
 *
 * Console interception is what makes this cover the app rather than the parts
 * somebody remembered to instrument. React Native reports a great deal through
 * `console.error` — unhandled promise rejections, render failures, native
 * module warnings — and none of it is reachable from a park.
 *
 * The originals are always called. Losing Metro's output would trade a problem
 * that only exists in the field for one that exists at every desk.
 */
export function installGlobalLogging(): void {
  const anyGlobal = globalThis as {
    ErrorUtils?: {
      getGlobalHandler(): (error: unknown, isFatal?: boolean) => void;
      setGlobalHandler(handler: (error: unknown, isFatal?: boolean) => void): void;
    };
  };

  const errorUtils = anyGlobal.ErrorUtils;
  if (errorUtils) {
    const previous = errorUtils.getGlobalHandler();
    errorUtils.setGlobalHandler((error, isFatal) => {
      log.error("app", isFatal ? "fatal error" : "uncaught error", error);
      // Flushed rather than left on the timer: a fatal one has no next tick.
      void log.flush();
      previous?.(error, isFatal);
    });
  }

  for (const method of ["error", "warn"] as const) {
    const original = console[method].bind(console);
    console[method] = (...args: unknown[]) => {
      log.fromConsole(method, args);
      original(...args);
    };
  }
}

function safeText(value: unknown): string {
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}
