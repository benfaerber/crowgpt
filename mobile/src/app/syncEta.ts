import type { SyncProgress } from "../sync/SyncEngine";

export interface SyncEstimate {
  /** 0..1 across the whole run. */
  fraction: number;
  bytesSent: number;
  bytesToSend: number;
  captureIndex: number;
  captureCount: number;
  /** Seconds remaining, or undefined while the estimate is still meaningless. */
  secondsLeft?: number;
  bytesPerSecond?: number;
}

const SMOOTHING = 0.25;
/** Below this, a rate says more about the first chunk's latency than the link. */
const MIN_SAMPLE_MS = 1500;
const MIN_SAMPLE_BYTES = 128 * 1024;

/**
 * Turns raw byte counts into a rate and a time remaining.
 *
 * Deliberately refuses to guess early: an ETA derived from the first chunk is
 * wildly wrong and visibly jumps around, which is worse than showing nothing.
 * Once it does have a rate it smooths it, because per-chunk rates on cellular
 * swing far too much to display directly.
 */
export class SyncEtaTracker {
  private startedAtMs = 0;
  private rate?: number;

  start(nowMs: number): void {
    this.startedAtMs = nowMs;
    this.rate = undefined;
  }

  observe(progress: SyncProgress, nowMs: number): SyncEstimate {
    const elapsedMs = nowMs - this.startedAtMs;
    const estimate: SyncEstimate = {
      fraction: progress.runFraction,
      bytesSent: progress.bytesSent,
      bytesToSend: progress.bytesToSend,
      captureIndex: progress.captureIndex,
      captureCount: progress.captureCount,
    };

    if (elapsedMs < MIN_SAMPLE_MS || progress.bytesSent < MIN_SAMPLE_BYTES) return estimate;

    const sample = progress.bytesSent / (elapsedMs / 1000);
    this.rate = this.rate === undefined ? sample : this.rate * (1 - SMOOTHING) + sample * SMOOTHING;
    if (this.rate <= 0) return estimate;

    const remaining = Math.max(0, progress.bytesToSend - progress.bytesSent);
    estimate.bytesPerSecond = this.rate;
    estimate.secondsLeft = remaining / this.rate;
    return estimate;
  }
}

export function formatDurationShort(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function formatRate(bytesPerSecond: number): string {
  if (bytesPerSecond >= 1024 * 1024) return `${(bytesPerSecond / 1024 / 1024).toFixed(1)} MB/s`;
  return `${Math.round(bytesPerSecond / 1024)} KB/s`;
}
