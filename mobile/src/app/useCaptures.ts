import { useCallback, useEffect, useRef, useState } from "react";

import { newClientUuid } from "../domain/ids";
import { deviceRandomBytes } from "../platform/random";
import type { CaptureRecord } from "../domain/types";
import { isPendingSync } from "../domain/types";
import type { AppServices } from "./AppServices";
import { log } from "./Log";
import { blockedFromSyncing } from "../domain/location";
import type { Compatibility } from "../domain/compatibility";
import { SyncEtaTracker, type SyncEstimate } from "./syncEta";

export interface CapturesView {
  captures: CaptureRecord[];
  /**
   * How many labels each capture has, for the queue and the row marker.
   *
   * Loaded with the list and refreshed with it, in one query rather than one
   * per row — the list asks this about everything on the phone every render.
   * A capture with no labels is absent rather than zero.
   */
  labelCounts: Map<string, number>;
  /** Which capture the run is uploading right now, for the row indicator. */
  syncingUuid?: string;
  pendingCount: number;
  syncing: boolean;
  progress?: SyncEstimate;
  lastMessage?: string;
  /** Warning when the server is old enough to be dropping fields silently. */
  compatibilityWarning?: string;
  /**
   * Why the store could not be read, when it could not.
   *
   * Distinct from an empty list on purpose: "there are no captures" and "I
   * could not find out" need different reactions, and only one of them is
   * cause for alarm.
   */
  readError?: string;
  refresh: () => Promise<void>;
  sync: () => Promise<void>;
  cancelSync: () => void;
  remove: (uuid: string) => Promise<void>;
  describe: (uuid: string, body: string) => Promise<CaptureRecord>;
}

/**
 * Reads the local store and drives sync from it.
 *
 * The store is the single source of truth for what the list shows — a sync
 * writes its results there and the view reloads, rather than the two keeping
 * separate ideas of the same capture.
 */
export function useCaptures(services: AppServices): CapturesView {
  const [captures, setCaptures] = useState<CaptureRecord[]>([]);
  const [labelCounts, setLabelCounts] = useState<Map<string, number>>(new Map());
  // Seeded from the engine, not from false: coming back to this screen during
  // a run must show the run, and a fresh `false` here is exactly the lie that
  // made a sync look stuck.
  const [syncing, setSyncing] = useState(() => services.syncEngine.isRunning);
  const [progress, setProgress] = useState<SyncEstimate | undefined>();
  const eta = useRef(new SyncEtaTracker());
  const currentCapture = useRef<string | undefined>(undefined);
  const [lastMessage, setLastMessage] = useState<string | undefined>();
  /** Set when the local store could not be read — never the same as "empty". */
  const [readError, setReadError] = useState<string | undefined>();
  const [compat, setCompatibility] = useState<Compatibility>({
    reachable: true,
    serverBehind: false,
  });

  /**
   * Re-read the local store.
   *
   * The catch is the point. This used to be `void refresh()` over an
   * uncaught promise: if reading the store threw, the rejection went nowhere,
   * `captures` stayed at its initial empty array, and the screen said "No
   * captures yet" — a failed read presented as an empty corpus. That is the
   * most alarming lie this app can tell, and it told it twice.
   */
  const refresh = useCallback(async () => {
    try {
      setCaptures(await services.repository.list());
      // Beside the rows rather than in its own effect: they are read together
      // and a queue counted from a stale list is a queue that lies.
      setLabelCounts(await services.labels.countsByCapture());
      setReadError(undefined);
    } catch (failure) {
      log.error("db", "reading the capture list failed", failure);
      setReadError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [services]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Follow the engine for as long as this screen exists. Mounting mid-run picks
  // the truth up; unmounting mid-run no longer throws it away.
  useEffect(() => {
    const engine = services.syncEngine;
    setSyncing(engine.isRunning);
    return engine.onRunningChanged((running) => {
      setSyncing(running);
      if (!running) void refresh();
    });
  }, [refresh, services]);

  /**
   * Captures left marked `syncing` by a run that is no longer happening.
   *
   * The state is written to the database when a capture's upload begins, so a
   * run that died — the app closed, the process was killed in a pocket — leaves
   * rows claiming to be in flight. Recovered at app start already; doing it
   * here too means a phone that has been sitting on the list for ten minutes
   * stops showing a spinner for something nobody is doing.
   */
  useEffect(() => {
    if (services.syncEngine.isRunning) return;
    void services.repository.recoverInterrupted().then((recovered) => {
      if (recovered > 0) void refresh();
    });
  }, [refresh, services]);

  /**
   * Claim back audio the app died in the middle of writing.
   *
   * Here rather than in AppServices.create so the list is on screen to refresh:
   * a capture that appears is the whole point, and one entered before the
   * screen existed would wait for some later reason to reload.
   */
  useEffect(() => {
    void services.recoverAbandonedCaptures().then((recovered) => {
      if (recovered > 0) void refresh();
    });
  }, [refresh, services]);

  const sync = useCallback(async () => {
    if (services.syncEngine.isRunning) return;
    setSyncing(true);
    setLastMessage(undefined);
    try {
      // Before enrolling, before anything: uploading recordings that name no
      // place at all would put rows in the corpus nobody can group later, and
      // this is the one setting where nothing else says where they were.
      const blocked = blockedFromSyncing(services.settings);
      if (blocked) {
        setLastMessage(blocked);
        return;
      }
      if (!services.isEnrolled) {
        await services.enroll();
      }
      // Before the push, not after: the point is to say the sync may not have
      // landed what it claims, and after the fact it reads as an excuse.
      const compatible = await services.checkCompatibility();
      setCompatibility(compatible);
      if (!compatible.reachable) {
        // Stop here rather than discovering it once per capture. Every request
        // in a run waits the full upload timeout before failing, so a phone out
        // of range spent half a minute per recording proving the same point —
        // which from the outside is a sync that has hung.
        setLastMessage("Server not reachable — nothing was sent.");
        return;
      }
      if (compatible.serverBehind && services.settings.strictSync) {
        // Stopping here leaves every capture pending, which is the honest
        // state — nothing was delivered. Syncing anyway would mark them done
        // while the server quietly dropped half of each one.
        setLastMessage("Sync stopped — server too old. Settings › Strict sync to override.");
        return;
      }
      eta.current.start(Date.now());
      const outcome = await services.syncEngine.syncAll({
        // Always. It was a setting, and the only thing switching it off
        // achieved was captures that upload and are never looked at — noticed,
        // if ever, by opening each one and finding nothing. The cost falls on
        // the server's worker, not on the phone or anybody's data.
        requestAnalysis: true,
        onProgress: (update) => {
          currentCapture.current = update.captureUuid;
          setProgress(eta.current.observe(update, Date.now()));
          // Reload as each capture finishes so rows settle into their final
          // state rather than all flipping at the end of the run.
          if (update.fraction >= 1) void refresh();
        },
      });
      log.info("sync", "run finished", {
        synced: outcome.synced.length,
        failed: outcome.failed.length,
        canceled: outcome.canceled,
        transcripts: outcome.transcripts,
      });
      for (const failure of outcome.failed) {
        log.warn("sync", `capture failed: ${failure.error}`, { capture: failure.uuid });
      }
      const parts: string[] = [];
      if (outcome.synced.length) parts.push(`${outcome.synced.length} synced`);
      if (outcome.failed.length) parts.push(`${outcome.failed.length} failed`);
      if (outcome.canceled) parts.push("stopped");
      // The run's downward step gets said too. A run that only fetched a
      // transcript used to report "Nothing to sync", which reads as the
      // transcript never coming — and was reported as exactly that.
      if (outcome.transcripts) {
        parts.push(outcome.transcripts === 1
          ? "1 transcript arrived"
          : `${outcome.transcripts} transcripts arrived`);
      }
      setLastMessage(parts.join(" · ") || "Nothing to sync");
    } catch (error) {
      log.error("sync", "run threw", error);
      setLastMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setProgress(undefined);
      setSyncing(false);
      // Last, and best-effort: the log rides along on a trip the phone was
      // making anyway, so the diagnostics for a bad afternoon in the field are
      // on the server before anyone thinks to ask for them. Its failure is
      // deliberately invisible — see AppServices.syncLogs.
      void services.syncLogs();
      // And pull the analysis down while there is still a network to pull it
      // from. The detections are wanted in a field, where there is not one.
      void services
        .prefetchAnalysis()
        .then((warm) =>
          warm.offline || warm.failed > 0
            ? log.warn("analysis", "cache warm incomplete", warm)
            : log.info("analysis", "cache warmed", warm),
        )
        .catch((failure) => log.warn("analysis", "cache warm failed", failure));
      await refresh();
    }
  }, [refresh, services]);

  const cancelSync = useCallback(() => {
    services.syncEngine.cancel();
  }, [services]);

  const remove = useCallback(
    async (uuid: string) => {
      await services.repository.remove(uuid);
      await refresh();
    },
    [refresh, services],
  );

  const describe = useCallback(
    async (uuid: string, body: string) => {
      const capture = await services.repository.get(uuid);
      const now = new Date().toISOString();
      const updated = await services.repository.update(uuid, {
        description: body,
        // Minted once and kept, so re-editing rewrites the same server-side note
        // instead of leaving a trail of near-duplicates.
        descriptionUuid: capture?.descriptionUuid ?? newClientUuid(deviceRandomBytes),
        descriptionUpdatedAt: now,
        // A synced capture with a fresh description owes the server something
        // again. Putting it back in the queue costs almost nothing: both creates
        // are idempotent and its bytes have already landed, so the retry sends
        // the note and no audio.
        ...(capture?.syncState === "synced" ? { syncState: "local" as const } : {}),
      });
      await refresh();
      return updated;
    },
    [refresh, services],
  );

  return {
    captures,
    describe,
    labelCounts,
    syncingUuid: currentCapture.current,
    pendingCount: captures.filter(isPendingSync).length,
    syncing,
    progress,
    lastMessage,
    compatibilityWarning: compat.warning,
    readError,
    refresh,
    sync,
    cancelSync,
    remove,
  };
}
