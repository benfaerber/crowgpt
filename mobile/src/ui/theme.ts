import { hasUnsyncedEdits } from "../domain/revision";
import type { CaptureRecord, SyncState } from "../domain/types";

/**
 * One dark palette, carried over from the Phase 0 screen. Field use is mostly
 * outdoors and often at dusk, so the app is dark-only by intent rather than by
 * omission — there is no light theme to fall back to.
 */
export const colors = {
  background: "#10141b",
  surface: "#1c2331",
  surfaceDeep: "#0b0e13",
  border: "#232c3b",
  text: "#e8eef7",
  textMuted: "#8b95a5",
  textFaint: "#5b6472",
  accent: "#2f6feb",
  /** A selected row, on the dark surface. Accent at low alpha reads as
   *  chosen without competing with the star or the sync badge. */
  selectedRow: "#1b2740",
  recording: "#c0392b",
  good: "#5ddc9a",
  warn: "#e8b84b",
  bad: "#ff8a7a",
} as const;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 20, xl: 32 } as const;

/**
 * Bottom padding for anything that scrolls.
 *
 * Every scrollable screen needs it and the amount is not a design choice: the
 * gesture bar sits over the bottom of the window, so a control flush with the
 * end of the content is one you cannot reliably press. Capture detail's Delete
 * button was the one that found this — last on the page, and blocked.
 *
 * A shared constant because the failure is per-screen and silent: whoever adds
 * the next screen will not think about it, and the bug only appears once
 * something important is last.
 */
export const pageEnd = 88;

export const radius = { sm: 6, md: 10, pill: 999 } as const;

export const syncStateLabels: Record<SyncState, string> = {
  local: "On phone",
  syncing: "Syncing",
  synced: "Synced",
  failed: "Failed",
};

export const syncStateColors: Record<SyncState, string> = {
  local: colors.textMuted,
  syncing: colors.accent,
  synced: colors.good,
  failed: colors.bad,
};

/**
 * How a capture is named out loud — "#86", or that it has no name yet.
 *
 * The server id, because that is the one every other part of this project uses:
 * the experiments resolve captures by it, `phases/` cites it, and Ben says
 * "capture 104" rather than a uuid nobody can read down a phone. It exists only
 * after a sync, so a local recording genuinely has no such name and the screen
 * must say that rather than invent one — a blank where an id goes reads as a
 * missing id, not an unsynced capture.
 *
 * One function so the row and the detail screen cannot drift, which is the same
 * lesson `syncBadge` below was written for.
 */
export function captureId(capture: CaptureRecord): string | undefined {
  return capture.serverCaptureId === undefined
    ? undefined
    : `#${capture.serverCaptureId}`;
}

/**
 * What a capture's sync badge should say, and in what colour.
 *
 * One function because there were two implementations: the list row knew that
 * an uploaded-then-edited capture reads "Edited", and the detail screen — the
 * screen you are *on* when you make the edit — did not, so it kept saying
 * "Synced" while the edit sat unpushed. That is precisely how a working sync
 * looks broken, and it cost a round of "is this even saving?".
 */
export function syncBadge(capture: CaptureRecord): { label: string; color: string } {
  const state = capture.syncState;
  const edited = state === "synced" && hasUnsyncedEdits(capture);
  return edited
    ? { label: "Edited", color: colors.textMuted }
    : { label: syncStateLabels[state], color: syncStateColors[state] };
}

// These two exist verbatim in dashboard/src/format.ts — same unit, same
// output, deliberately not a shared package (its header says why). They began
// as copies and drifted into different units, which is the one way a "copy"
// can actually hurt: code moved between the apps compiled fine and showed
// durations a thousand times off. Change one, change the other.
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  const total = Math.round(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function formatRecordedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
