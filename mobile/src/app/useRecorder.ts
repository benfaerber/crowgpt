import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { currentBuild } from "./buildInfo";
import { micState, shouldReopenSession } from "../domain/micState";
import { newClientUuid } from "../domain/ids";
import {
  addPending,
  settlePending as dropPending,
  type PendingCapture,
} from "../domain/pendingCaptures";
import { stickyCaptureDefaults } from "../domain/settings";
import { idleConfigFrom } from "../domain/idle";
import { planDictation, shouldReopenListening } from "../domain/dictationSession";
import { deviceRandomBytes } from "../platform/random";
import type { NewCapture } from "../domain/types";
import type { AppServices } from "./AppServices";
import { PRE_ROLL_SEC, type InputsChange } from "../recording/Recorder";
import type { DictationControl, IdleControl, RecorderView } from "./recorderView";
import { log } from "./Log";
import { wantsFix } from "../domain/location";
import { withTimeout } from "../domain/timeout";
import { FIX_TIMEOUT_MS } from "../recording/LocationProvider";

/**
 * How long the press guard may be held before an ignored press is suspicious.
 *
 * Opening or closing a microphone is well under a second, and a double tap is
 * milliseconds. Three seconds is longer than anything healthy and shorter than
 * a person's patience, so a guard still held at this point is the thing that
 * makes the button look broken rather than the thing that keeps it safe.
 */
const STUCK_PRESS_MS = 3_000;

/**
 * Drives the record button and, on stop, commits the capture to the local
 * store.
 *
 * That write is the moment the capture becomes real: it happens before anything
 * touches the network, and it is what makes the rest of the app local-first
 * rather than a UI over an upload queue.
 */
export function useRecorder(services: AppServices, onRecorded: () => void): RecorderView {
  const [recording, setRecording] = useState(false);
  const [listening, setListening] = useState(false);
  const [bufferedMs, setBufferedMs] = useState(0);
  const [level, setLevel] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | undefined>();
  const unsubscribe = useRef<(() => void) | null>(null);
  const startedAt = useRef(0);
  /** True while a start or stop is still in flight. See `toggle`. */
  const busy = useRef(false);
  /** When it was taken, so a held guard can be told from a double tap. */
  const busySince = useRef(0);
  const preRollMs = useRef(0);
  const listeningSince = useRef(0);
  /**
   * True while the buffer is being reopened on a microphone that was just
   * plugged in. Plugging one device in can fire several input-changed events,
   * and each would otherwise start its own stop/start against a session the
   * previous one was still tearing down.
   */
  const switching = useRef(false);
  const fix = useRef<ReturnType<AppServices["location"]["current"]> | null>(null);
  /**
   * True while the recording in flight was started by the idle trigger
   * rather than a person. Set by the onIdle handler just before it presses
   * the button, read once at stop, and cleared on any failed start — a stale
   * true would brand the recordist's own next capture as automatic.
   */
  const autoTrigger = useRef(false);

  const [pending, setPending] = useState<PendingCapture[]>([]);
  const pendingSeq = useRef(0);
  const beginPending = useCallback(
    (kind: PendingCapture["kind"], durationMs?: number) => {
      const id = `pending-${(pendingSeq.current += 1)}`;
      setPending((current) => addPending(current, { id, kind, durationMs }));
      return id;
    },
    [],
  );
  const settlePending = useCallback((id: string) => {
    setPending((current) => dropPending(current, id));
  }, []);
  /**
   * The last thing a press got as far as.
   *
   * A press that never finishes holds the guard and kills the button, and from
   * outside every one of those looks identical. This is the only thing that
   * says WHICH await it is sitting in — and the awaits here reach native code
   * and the network, so "which one" is the whole question.
   */
  const step = useRef("idle");

  // Subscribing is idempotent here because the meter runs while listening too,
  // and start() must not stack a second subscription on top of that one.
  const meterOn = useCallback(() => {
    if (!unsubscribe.current) unsubscribe.current = services.recorder.onLevel(setLevel);
  }, [services]);

  const meterOff = useCallback(() => {
    unsubscribe.current?.();
    unsubscribe.current = null;
    setLevel(0);
  }, []);

  useEffect(() => {
    if (!recording) return;
    const timer = setInterval(
      () => setElapsedMs(preRollMs.current + Date.now() - startedAt.current),
      250,
    );
    return () => clearInterval(timer);
  }, [recording]);

  // How much past is actually available — the buffer starts empty and fills in
  // real time, so a button pressed two seconds after arriving on the screen
  // reaches back two seconds, not fifteen.
  useEffect(() => {
    if (!listening || recording) return;
    const tick = () => {
      const held = Math.min(PRE_ROLL_SEC * 1000, Date.now() - listeningSince.current);
      setBufferedMs(held);
      return held;
    };
    if (tick() >= PRE_ROLL_SEC * 1000) return;
    const timer = setInterval(() => {
      if (tick() >= PRE_ROLL_SEC * 1000) clearInterval(timer);
    }, 250);
    return () => clearInterval(timer);
  }, [listening, recording]);

  const preRollEnabled = services.settings.preRoll;
  const inBackground = services.settings.backgroundListening;
  /**
   * The same flag, readable without being a dependency.
   *
   * The session effect below must not re-run when pocket listening is toggled:
   * its cleanup stops the microphone, and `stopListening` is asynchronous — so
   * the body ran first, found the session still open, adopted it, and then the
   * stop landed and closed the microphone under it. Switching pocket listening
   * on therefore turned the microphone *off*, which is the opposite of the
   * feature. The mode is changed by the effect after it instead.
   */
  const backgroundRef = useRef(inBackground);
  backgroundRef.current = inBackground;

  /**
   * The microphone this recording would use, and whether it is the first choice.
   *
   * Said before the button, not after. Afterwards it is only in the capture's
   * metadata, which nobody reads while a crow is calling — and "I thought I was
   * recording on the Rode" is a discovery best made at the door.
   */
  const [micNote, setMicNote] = useState<string | undefined>();
  /**
   * Which microphone is on, named on the screen rather than two taps away.
   *
   * "Mic open" says the app is listening; it does not say what it is listening
   * *through*, and that is the difference between a capture worth keeping and
   * one recorded down a Bluetooth headset by accident. It is already stamped on
   * every capture afterwards — this is the same fact, before the recording
   * rather than after.
   */
  const [micLabel, setMicLabel] = useState<string | undefined>();
  const [notice, setNotice] = useState<string | undefined>();

  /**
   * Pocket listening without a notification is the thing this app promised not
   * to do.
   *
   * Android will not show one without POST_NOTIFICATIONS, and it will still run
   * the service — so a refused permission leaves the microphone held from a
   * pocket with nothing on screen to say so. That is not a state to be quiet
   * about, whatever the setting says.
   */
  useEffect(() => {
    let live = true;
    void services.permissions
      .list()
      .then((entries) => {
        if (!live) return;
        // The microphone first, and whatever the other settings say: without it
        // nothing records at all. Measured on the Pixel 8 — revoking it while
        // pocket listening killed the app, and the relaunched app showed a
        // normal capture screen with a silent microphone behind it. "READY" and
        // "cannot record" looked identical.
        const microphone = entries.find((entry) => entry.key === "microphone");
        if (microphone && microphone.state !== "granted") {
          setNotice(
            "Microphone permission is not granted — nothing can be recorded. "
            + "Settings › Permissions.",
          );
          log.warn("recorder", "microphone permission is not held", {
            state: microphone.state,
          });
          return;
        }
        if (!inBackground) {
          setNotice(undefined);
          return;
        }
        const notifications = entries.find((entry) => entry.key === "notifications");
        if (!notifications || notifications.state === "granted") {
          setNotice(undefined);
          return;
        }
        setNotice(
          "Pocket mic is on but notifications are blocked — the microphone will "
          + "be held with nothing on screen to say so. Settings › Permissions.",
        );
        log.warn("recorder", "pocket listening without a visible notification", {
          state: notifications.state,
        });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
    // `recording` so the check runs again after a capture: a permission revoked
    // mid-session is exactly the case this is for.
  }, [inBackground, recording, services]);
  useEffect(() => {
    let live = true;
    const check = (change?: InputsChange) => {
      if (change?.reason === "removed") noteRemoval(change);
      void services.refreshMicrophones().then(async () => {
        if (!live) return;
        // Ordered: switching sessions changes the answer the note describes,
        // so a note written first would describe the session just replaced.
        await adoptNewMicrophone();
        if (live) decideMicNote();
      });
    };
    check();
    // Re-check when a microphone is plugged in or pulled out. The input list is
    // cached — asking Android for it was moved off the JS thread for being slow
    // — so without this the note said "isn't connected" until Settings was
    // opened or a recording started, which is exactly when somebody has just
    // plugged the mic in and is looking at this screen.
    const stop = services.recorder.onInputsChanged?.(check);
    return () => {
      live = false;
      stop?.();
    };

    /**
     * Write down what the phone did about a microphone leaving.
     *
     * The disconnect cue is decided natively, inside an audio device callback,
     * at a moment nobody is looking at the screen — and the first version of it
     * stayed silent in the field with nothing anywhere to say why. There are
     * three different silences (the removal did not match the mic in use, the
     * phrase had never been rendered so it could only beep, or it spoke into
     * earbuds that were gone) and this is the only line that tells them apart.
     */
    function noteRemoval(change: InputsChange) {
      log.info("recorder", "a microphone was unplugged", {
        removed: change.removedTypes,
        inUse: change.routedTypes,
        sessionOpen: change.routeLive,
        cue: change.said ?? "stayed quiet",
        // The two fields that tell "words" apart from silence claimed as
        // words: where the player was actually routed, and whether the focus
        // grant that clears a fade was granted. Cost a field session when the
        // first version of this line dropped them.
        cueRoute: change.cueRoute,
        cueFocus: change.cueFocus,
      });
    }

    /**
     * Reopen the buffer on the microphone that was just plugged in.
     *
     * A session pins its device when it opens and cannot be re-pointed, so the
     * only way onto a microphone that arrived afterwards is a new session. That
     * costs whatever the ring was holding — up to {@link PRE_ROLL_SEC} seconds
     * — which is why it is worth being deliberate about when it happens rather
     * than reopening on every event.
     *
     * The trade is the right way round. Plugging a microphone in is an explicit
     * act, and it is nearly always followed by wanting to record through it;
     * carrying on holding a buffer from the phone mic honours neither. An empty
     * ring is visible on the button, which says "buffering…" until it fills. A
     * capture recorded through the wrong microphone is visible to nobody until
     * it is played back.
     *
     * Through `swapListening`, never a stop/start pair. Stopping takes the
     * foreground service down, and a backgrounded app cannot start a new one
     * (Android 12+) — so the pair killed pocket listening on every route
     * change with music playing, which is exactly when earbuds change routes.
     * The swap recreates the session under the live service instead.
     */
    async function adoptNewMicrophone() {
      const recorder = services.recorder;
      if (switching.current) return;
      const session = recorder.activeInput?.() ?? null;
      const wanted = services.microphoneNow();
      if (!session || !shouldReopenSession(session, wanted)) return;
      // Asked separately from `session.recording`: the two are published by
      // different parts of the recorder, and a capture that started between the
      // check above and here must still not be torn down.
      if (recorder.isRecording?.()) return;
      if (!recorder.swapListening) return;

      switching.current = true;
      try {
        setBufferedMs(0);
        await recorder.swapListening({ input: wanted, preRollSeconds: PRE_ROLL_SEC });
        listeningSince.current = Date.now();
        meterOn();
        setListening(true);
        log.info("recorder", "adopted the new microphone", {
          from: session.routed,
          to: wanted,
        });
      } catch (failure) {
        // The buffer is closed, did not reopen, and the native side has stood
        // the service down. Said on the screen *and* in the ears: the swap
        // fires from a pocket as often as not, where the screen says nothing
        // and a silently dead buffer is this feature's worst outcome.
        setListening(false);
        meterOff();
        log.error("recorder", "could not reopen on the new microphone", failure, {
          from: session.routed,
          to: wanted,
        });
        setError(failure instanceof Error ? failure.message : String(failure));
        void recorder.playCue?.("failed");
      } finally {
        switching.current = false;
      }
    }

    function decideMicNote() {
      // One derivation, shared with the settings picker. This screen used to
      // work the answer out for itself and got it confidently wrong: it named
      // whichever microphone the list resolved to *now*, which is a claim about
      // the next recording, while the open session stayed on the one it pinned.
      const state = micState({
        priority: services.settings.micPriority,
        attached: services.recorder.listInputs?.() ?? [],
        session: services.recorder.activeInput?.() ?? null,
      });
      setMicLabel(state.label);
      setMicNote(state.warning);
    }
    // `listening` as well as `recording`: opening a session is what turns this
    // from a prediction into a fact, and the caption has to change with it.
  }, [services, recording, listening]);

  /**
   * Hold the mic open for as long as the setting is on — not just this screen.
   *
   * It used to stop the moment you navigated away, on the reasoning that an app
   * should never quietly hold the microphone from behind another screen. A
   * foreground service changes that calculus: the mic is now held with an
   * ongoing notification that cannot be dismissed, so it is not quiet, and
   * screen-scoping merely broke the feature in the situation it was built for.
   * A fledgling called while the phone was in a pocket and the ring was empty,
   * because Android had revoked the microphone the moment the screen slept.
   *
   * Stopping is now the setting's job, and Android's when the app dies.
   */
  useEffect(() => {
    const recorder = services.recorder;
    const startListening = recorder.startListening?.bind(recorder);
    if (!preRollEnabled || !startListening) {
      // Covers turning the setting off, which is the only deliberate stop.
      void recorder.stopListening?.().catch((failure) =>
        log.warn("recorder", "stopListening failed — the microphone may still be held", failure));
      setListening(false);
      setBufferedMs(0);
      return;
    }
    // Already running from a previous screen: adopt it rather than opening a
    // second one, which the native side refuses outright.
    if (recorder.isListening?.()) {
      meterOn();
      setListening(true);
      return;
    }
    let cancelled = false;
    void (async () => {
      if (!(await recorder.requestPermission())) {
        log.warn("recorder", "microphone permission denied while starting to listen");
        setError("Microphone permission denied");
        return;
      }
      if (cancelled) return;
      // Which microphones exist is a fact about this moment, and asking costs
      // a trip to the audio HAL — so it is asked here, off the render path.
      await services.refreshMicrophones();
      if (cancelled) return;
      try {
        await startListening({
          input: services.microphoneNow(),
          preRollSeconds: PRE_ROLL_SEC,
          // Read now rather than captured: this effect no longer re-runs when
          // the mode changes, so the closure's copy could be a session old.
          background: backgroundRef.current,
        });
        if (cancelled) {
          await recorder.stopListening?.().catch((failure) =>
            log.warn("recorder", "stopListening failed — the microphone may still be held", failure));
          return;
        }
        listeningSince.current = Date.now();
        meterOn();
        setListening(true);
        log.info("recorder", "listening", {
          background: backgroundRef.current,
          preRollSec: PRE_ROLL_SEC,
          input: services.microphoneNow(),
        });
      } catch (failure) {
        // The silent failure this whole feature exists to prevent: a mic that
        // never opened looks exactly like a mic that opened and heard nothing.
        log.error("recorder", "startListening failed", failure, {
          background: backgroundRef.current,
        });
        setError(failure instanceof Error ? failure.message : String(failure));
      }
    })();
    return () => {
      cancelled = true;
      // With background listening on, leaving the screen is not a request to
      // stop — the service and its notification are what make holding the
      // microphone honest, and closing it here is what lost the fledgling.
      //
      // With it off there is no service, so Android revokes the microphone the
      // moment the app stops being visible anyway. Closing it deliberately is
      // tidier than being closed by the system, and leaves nothing on screen
      // pretending to listen.
      if (!backgroundRef.current) {
        setListening(false);
        setBufferedMs(0);
        meterOff();
        void recorder.stopListening?.().catch((failure) =>
        log.warn("recorder", "stopListening failed — the microphone may still be held", failure));
      }
    };
    // Deliberately without `inBackground`: see backgroundRef above. Tearing the
    // session down to change a flag on it is what broke pocket listening.
  }, [meterOff, meterOn, preRollEnabled, services]);

  /**
   * Follow the pocket-listening setting while the microphone is already open.
   *
   * The mode used to be read only when a session started, and the effect that
   * starts one adopts an existing session rather than restarting it — so
   * turning pocket listening *off* changed nothing at all. The service kept
   * running, the notification kept showing, and the microphone stayed open
   * behind a phone that had been told to stop.
   */
  useEffect(() => {
    if (!listening) return;
    void services.recorder
      .setBackground?.(inBackground)
      .then((holding) => {
        // Says what actually happened rather than what was asked for. "Switch
        // on, nothing happens" was invisible for a whole afternoon.
        log.info("recorder", inBackground ? "pocket listening on" : "pocket listening off", {
          serviceHolding: holding,
          listening,
        });
      })
      .catch((failure) => {
        log.warn("recorder", "could not change background listening", failure);
      });
  }, [inBackground, listening, services]);

  /**
   * Close the microphone when the app leaves the screen, unless pocket
   * listening is on.
   *
   * "Only while the app is on screen" was being left to Android, which does not
   * close the microphone — it *silences* it. The recording session stayed open,
   * so the privacy indicator stayed lit and the phone still listed the app as
   * using the mic. Switching pocket listening off and walking away therefore
   * looked exactly like leaving it on.
   *
   * Reopened on return, because the rolling buffer is the reason the setting
   * exists and a phone that quietly stopped buffering after one trip to the
   * home screen would be worse than one that never buffered at all.
   */
  // Only ever reopens what this listener itself closed. Asking "is it listening
  // right now?" is not the same question: at launch the session effect's own
  // start is still in flight, so both fired and the second was refused with
  // ERR_LISTEN_START — harmless, logged, and pure noise.
  const closedOnLeaving = useRef(false);

  useEffect(() => {
    if (!preRollEnabled) return;
    const subscription = AppState.addEventListener("change", (next) => {
      const recorder = services.recorder;
      if (next === "active") {
        if (closedOnLeaving.current && !recorder.isRecording?.()) {
          closedOnLeaving.current = false;
          void recorder
            .startListening?.({
              input: services.microphoneNow(),
              preRollSeconds: PRE_ROLL_SEC,
              background: backgroundRef.current,
            })
            .then(() => {
              listeningSince.current = Date.now();
              meterOn();
              setListening(true);
            })
            .catch((failure) => log.warn("recorder", "could not resume listening", failure));
        }
        return;
      }
      // Backgrounded. A recording in progress is a deliberate act and keeps the
      // microphone whatever this setting says — stopping that would throw away
      // audio somebody asked for. An armed idle session likewise: it holds
      // its own service, and going home to wait out the hour is the intended
      // use, not a request to stop.
      if (backgroundRef.current || idleArmedRef.current || recorder.isRecording?.()) return;
      closedOnLeaving.current = true;
      setListening(false);
      setBufferedMs(0);
      meterOff();
      void recorder.stopListening?.().catch((failure) =>
        log.warn("recorder", "stopListening failed — the microphone may still be held", failure));
      log.info("recorder", "microphone closed on leaving the app");
    });
    return () => subscription.remove();
  }, [meterOff, meterOn, preRollEnabled, services]);

  useEffect(() => () => unsubscribe.current?.(), []);

  const start = useCallback(async (cued: boolean) => {
    step.current = "start:permission";
    if (!(await services.recorder.requestPermission())) {
      setError("Microphone permission denied");
      // The one refusal that never throws, so the catch in perform() cannot
      // say it. Unsaid, a headset press against a revoked permission sounds
      // exactly like a recording.
      if (cued) void services.recorder.playCue?.("failed");
      return;
    }
    // Captured before the native call: once recording begins the buffer has
    // been drained into the file, and this is the only record of how much of
    // the recording predates the press.
    preRollMs.current = listening ? bufferedMs : 0;
    meterOn();
    step.current = "start:refresh-mics";
    await services.refreshMicrophones();
    // Resolved now, not at settings time: which microphone is present is a
    // fact about this moment.
    step.current = "start:native";
    await services.recorder.start({ input: services.microphoneNow() });
    step.current = "start:started";
    // After the native start, not before: the tone confirms the microphone is
    // open, and it is the only part of this the recordist can perceive.
    if (cued) void services.recorder.playCue?.("started");
    // Started, not awaited: a GPS fix can take seconds and must never delay the
    // start of a recording. It is collected by the time the user stops.
    //
    // Not started at all when the recordist asked for region only: the cheapest
    // way to keep a promise about coordinates is to never have any.
    fix.current = wantsFix(services.settings.locationPrecision)
      ? services.location.current()
      : Promise.resolve(undefined);
    startedAt.current = Date.now();
    setElapsedMs(preRollMs.current);
    setRecording(true);
  }, [bufferedMs, listening, meterOn, services]);

  /**
   * Everything about a capture that is not the microphone.
   *
   * Its own function because it must not be awaited by the press guard — see
   * above — and because a failure in here must never look like a failed
   * recording. The audio is already on disk and safe by the time this runs.
   */
  const fileCapture = useCallback(async ({
    summary, endedAt, build, pending, placeholder, auto,
  }: {
    summary: Awaited<ReturnType<AppServices["recorder"]["stop"]>>;
    endedAt: number;
    build: ReturnType<typeof currentBuild>;
    pending: ReturnType<AppServices["location"]["current"]> | null;
    placeholder: string;
    /** The idle trigger pressed the button, not a person. */
    auto: boolean;
  }) => {
    // Deliberately does not touch `step`: that breadcrumb belongs to whatever
    // press is in flight now, and this runs alongside the next one.
    try {
      const where = await withTimeout(
        pending ?? Promise.resolve(undefined),
        FIX_TIMEOUT_MS,
        undefined,
      );
      // The region is recorded whatever the precision — it is what a capture
      // says about place once the coordinates are gone, and resolving it later
      // from a fix that no longer exists is not possible.
      const home = services.settings.homeRegion.trim() || undefined;
      // Still bounded, though nothing is waiting on it any more: a resolver that
      // never answers would otherwise leave a "Loading…" row up forever.
      const resolved = where
        ? await withTimeout(services.regionFor(where), FIX_TIMEOUT_MS, undefined)
        : undefined;

      const capture: NewCapture = {
        uuid: newClientUuid(deviceRandomBytes),
        mediaUuid: newClientUuid(deviceRandomBytes),
        recordedAt: new Date(endedAt - summary.durationMs).toISOString(),
        durationMs: summary.durationMs,
        sampleRate: summary.sampleRate,
        channels: summary.channels,
        audioPath: summary.path,
        bytes: summary.bytes,
        latitude: where?.latitude,
        longitude: where?.longitude,
        region: resolved ?? home,
        // Stored with the capture, not read from the setting later: the setting
        // says what was requested, and the failure worth catching is a request
        // that wasn't honoured.
        inputDevice: summary.device ?? undefined,
        inputHonoured: summary.inputHonoured ?? undefined,
        preRollSec: summary.preRollSec,
        // The last capture's answers carried forward as this one's
        // pre-selection — still per capture, still editable on its screen.
        // Not for an auto capture: the sticky role and distance describe the
        // recordist standing somewhere, and nobody was standing anywhere. An
        // unattended phone inheriting "feeder, under 10 m" from last weekend
        // is a wrong answer that looks exactly like a real one.
        ...(auto ? { trigger: "auto" as const } : stickyCaptureDefaults(services.settings)),
        // Stamped here rather than read off the device row at sync time: this is
        // the build that made the audio, and the device row will have moved on.
        appVersion: build.version > 0 ? build.version : undefined,
        appCommit: build.version > 0 ? build.commit : undefined,
      };
      await services.repository.add(capture);
      if (summary.failure) {
        // The recording stopped before the person did. Said out loud on the
        // screen and written to the log, because a short file that looks like a
        // normal capture is the worst way to find this out — a fortnight later,
        // wondering why the call is not in it.
        log.error("recorder", `capture ended early: ${summary.failure}`, undefined, {
          uuid: capture.uuid,
          durationMs: summary.durationMs,
        });
        setError(`Recording stopped early — ${summary.failure}`);
      }
      log.info("recorder", "capture written", {
        uuid: capture.uuid,
        durationMs: capture.durationMs,
        bytes: capture.bytes,
        preRollSec: capture.preRollSec,
        input: capture.inputDevice,
        inputHonoured: capture.inputHonoured,
        trigger: capture.trigger,
      });
      onRecorded();
    } catch (failure) {
      // Never rethrown: this no longer runs inside `perform`, so there is no
      // catch above it, and an unhandled rejection here would be the silent
      // loss of a capture whose audio is sitting on disk.
      log.error("recorder", "could not file the capture", failure, {
        durationMs: summary.durationMs,
        path: summary.path,
      });
      setError("The recording was saved but could not be entered — see the log.");
    } finally {
      settlePending(placeholder);
    }
  }, [onRecorded, services, settlePending]);

  const stop = useCallback(async (cued: boolean) => {
    step.current = "stop:native";
    const summary = await services.recorder.stop();
    step.current = "stop:stopped";
    // Read here, not where the capture is built: the GPS fix and the region
    // lookup sit in between, so the clock down there is the clock *after* the
    // wait. A capture was dated by when its metadata finished rather than when
    // its audio did — nothing outdoors with a fix already in hand, up to
    // FIX_TIMEOUT_MS indoors, and never visible from the row afterwards.
    const endedAt = Date.now();
    // The audio is on disk and its length is known, so the list can show it
    // now rather than after the fix, the region and the write. Everything below
    // is bookkeeping about a recording that already exists.
    // Settled by `fileCapture`'s finally, which is the thing it stands for.
    // A placeholder outliving that work is a permanent "Loading…" over a capture
    // that will never arrive, which is a worse lie than the gap it closes.
    const placeholder = beginPending("audio", summary.durationMs);
    // Cued here, not at the end: the GPS fix below can take seconds, and the
    // tone confirms the file — which is closed — rather than the metadata.
    // A capture that ended early gets the failure tone instead, because a
    // truncated recording discovered at home is this feature's worst outcome.
    if (cued) void services.recorder.playCue?.(summary.failure ? "failed" : "stopped");
    const build = currentBuild();
    setRecording(false);
    if (listening) {
      // The mic stays open and the buffer starts refilling from empty: crows
      // call in bouts, and the second call is missed as easily as the first.
      listeningSince.current = Date.now();
      setBufferedMs(0);
    } else {
      meterOff();
    }

    // Taken and cleared before it is handed on, and now load-bearing rather
    // than careful: a new recording may legitimately start while this one is
    // still being written up — that is the whole point of the change below —
    // and starting one reassigns `fix.current`. Reading it any later would
    // collect the NEXT capture's fix for this one.
    const pending = fix.current;
    fix.current = null;
    // Read and cleared here, like the fix: the next recording may start while
    // this one is still being filed, and it owns the flag from then on.
    const auto = autoTrigger.current;
    autoTrigger.current = false;
    // THE GUARD ENDS HERE, and this is the bug the log finally named. Everything
    // below waits on a GPS fix, a region lookup and a write, and `perform` used
    // to hold `busy` across all of it — so a fix that took its time left the
    // button doing nothing for up to FIX_TIMEOUT_MS. Worse, `setRecording(false)`
    // has already run by this point, so the screen says STBY and looks ready:
    // the recordist sees an idle button that ignores every press. Ben's report,
    // exactly, and the third rapid take is when it bites because the fix that
    // take started has had a second and a half to resolve rather than ten.
    //
    // Detaching is safe because the microphone is already closed: the one thing
    // the guard exists to serialise is starting and stopping the recorder, and
    // that is done. `summary` and the fix are local, and the uuid is minted
    // below, so a capture written while the NEXT one records cannot collide.
    // The placeholder is what stands in the list meanwhile.
    void fileCapture({ summary, endedAt, build, pending, placeholder, auto });
  }, [beginPending, fileCapture, listening, meterOff, services]);


  /**
   * Recording a spoken note.
   *
   * Lives here rather than on a screen because this hook is the only thing that
   * owns the listening session and the press guard. A screen calling
   * `stopListening` itself would race the session effect, and a Record press
   * during a note would reach Kotlin and hit `check(!recording)`.
   *
   * The sequence is forced by the recorder: `WavRecorder.start` reuses an open
   * listening session and drains the pre-roll ring into whatever it opens, so a
   * note started over a live buffer would carry fifteen seconds of bird audio at
   * its head and empty the ring. Close, record, reopen — and say what that costs
   * before the tap rather than after.
   */
  const [dictationPhase, setDictationPhase] =
    useState<DictationControl["phase"]>("idle");
  const [dictationCapture, setDictationCapture] = useState<string | undefined>();
  const [ringLossMs, setRingLossMs] = useState(0);
  const [dictationError, setDictationError] = useState<string | undefined>();
  const dictationStartedAt = useRef(0);
  /** The row being written, so stop() can finish the one start() opened. */
  const dictationRow = useRef<string | undefined>(undefined);
  /** Whether this note closed the buffer, so only what we closed is reopened. */
  const closedForDictation = useRef(false);
  /** True for the whole note, so a session failure is routed to its stop path. */
  const dictating = useRef(false);

  const reopenBuffer = useCallback(async () => {
    if (!shouldReopenListening({
      wasListening: closedForDictation.current,
      preRollEnabled,
    })) return;
    closedForDictation.current = false;
    try {
      await services.recorder.startListening?.({
        input: services.microphoneNow(),
        preRollSeconds: PRE_ROLL_SEC,
        background: backgroundRef.current,
      });
      listeningSince.current = Date.now();
      setBufferedMs(0);
      meterOn();
      setListening(true);
    } catch (failure) {
      // The expensive silence. A dictation is a deliberate stop/start pair,
      // which re-enters the hazard `swapListening` exists for — a backgrounded
      // app cannot start a foreground service on Android 12+. If the buffer does
      // not come back, the microphone is dead and the screen looks normal, so
      // this is said on screen AND in the ears.
      setListening(false);
      meterOff();
      log.error("recorder", "the buffer did not reopen after a spoken note", failure);
      setDictationError(
        "The rolling buffer did not reopen. Record still works, but it will not "
        + "reach back — leave and return to this screen to restart it.");
      void services.recorder.playCue?.("failed");
    }
  }, [meterOff, meterOn, preRollEnabled, services]);

  const startDictation = useCallback(async (captureUuid: string) => {
    if (busy.current) return;
    const decision = planDictation({
      listening, recording, bufferedMs,
    });
    if (!decision.ok) {
      setDictationError(decision.reason);
      return;
    }
    busy.current = true;
    busySince.current = Date.now();
    step.current = "dictation:begin";
    setDictationError(undefined);
    try {
      if (!(await services.recorder.requestPermission())) {
        setDictationError("Microphone permission denied");
        return;
      }
      setRingLossMs(decision.ringLossMs);
      if (decision.closeListening) {
        setDictationPhase("closing");
        step.current = "dictation:close-buffer";
        await services.recorder.stopListening?.();
        closedForDictation.current = true;
        setListening(false);
        setBufferedMs(0);
        meterOff();
        log.info("recorder", "buffer closed for a spoken note", {
          ringLossMs: decision.ringLossMs, captureUuid,
        });
      }
      step.current = "dictation:native";
      const path = await services.recorder.start({
        input: services.microphoneNow(),
        // The whole orphan guard. Without it a killed process leaves a file the
        // sweep enters into the corpus as a field capture.
        prefix: "dictation_",
      });
      if (typeof path !== "string") throw new Error("the recorder returned no path");
      const uuid = newClientUuid(deviceRandomBytes);
      // Written before a byte is in it: this row is what says a process died
      // holding the pen, and what keeps the path out of the sweep's reach.
      await services.addDictation({
        uuid, captureUuid, audioPath: path,
        recordedAt: new Date().toISOString(),
        durationMs: 0, bytes: 0, sampleRate: 48_000, channels: 1,
        state: "recording",
      });
      dictationRow.current = uuid;
      dictating.current = true;
      dictationStartedAt.current = Date.now();
      setDictationCapture(captureUuid);
      setDictationPhase("recording");
      meterOn();
    } catch (failure) {
      log.error("recorder", "could not start a spoken note", failure);
      setDictationError(failure instanceof Error ? failure.message : String(failure));
      setDictationPhase("idle");
      dictating.current = false;
      await reopenBuffer();
    } finally {
      step.current = "idle";
      busy.current = false;
    }
  }, [bufferedMs, listening, meterOff, meterOn, recording, reopenBuffer, services]);

  const stopDictation = useCallback(async () => {
    if (busy.current) return;
    const uuid = dictationRow.current;
    if (!uuid) return;
    busy.current = true;
    busySince.current = Date.now();
    step.current = "dictation:stop";
    setDictationPhase("saving");
    try {
      const summary = await services.recorder.stop();
      await services.dictations.update(uuid, {
        durationMs: summary.durationMs,
        bytes: summary.bytes,
        sampleRate: summary.sampleRate,
        channels: summary.channels,
        inputDevice: summary.device ?? undefined,
        inputHonoured: summary.inputHonoured ?? undefined,
        state: "ready",
      });
      log.info("recorder", "spoken note written", {
        uuid, durationMs: summary.durationMs, bytes: summary.bytes,
      });
    } catch (failure) {
      log.error("recorder", "could not finish a spoken note", failure);
      setDictationError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      dictationRow.current = undefined;
      dictating.current = false;
      meterOff();
      setDictationPhase("reopening");
      await reopenBuffer();
      setDictationPhase("idle");
      setDictationCapture(undefined);
      setRingLossMs(0);
      step.current = "idle";
      busy.current = false;
      onRecorded();
    }
  }, [meterOff, onRecorded, reopenBuffer, services]);

  const perform = useCallback(async (cued: boolean) => {
    // THE LINE THAT ANSWERS THE FIRST QUESTION, and it is written before every
    // guard on purpose. When the button "does nothing" there are two completely
    // different failures and no way to tell them apart afterwards: the press
    // never reached JS at all (something over the button, or a JS thread that
    // has stopped answering), or it arrived and was dropped. Its ABSENCE from
    // the log is therefore the finding — so nothing above it may return early.
    //
    // The native pair matter as much as ours: `recording` is what this hook
    // believes and `nativeRecording` is what the microphone is actually doing,
    // and a button that looks idle over a live recording is the two disagreeing.
    log.info("recorder", "record pressed", {
      cued,
      recording,
      listening,
      busyHeldMs: busy.current ? Date.now() - busySince.current : 0,
      nativeRecording: services.recorder.isRecording?.() ?? null,
      nativeListening: services.recorder.isListening?.() ?? null,
    });
    // A second tap while the first is still in flight used to reach Kotlin and
    // come back as "already recording" — caught and shown as an error, over a
    // recording that had in fact started perfectly well. Opening a microphone
    // takes a moment and a finger is faster than that. No cue either way: the
    // first press is still doing the work, and it will say how it went.
    if (busy.current) {
      // Dropping the press is right; dropping it in silence is what made a dead
      // button undiagnosable. A finger is faster than a microphone, so the
      // ordinary case is a double tap milliseconds apart and worth no noise —
      // but the guard is only ever released by the `finally` below, so anything
      // that never settles holds it forever and every press after that
      // disappears with no error, no cue and no log. The two are told apart by
      // how long it has been held, which is the only thing that distinguishes
      // them from outside.
      const heldMs = Date.now() - busySince.current;
      if (heldMs > STUCK_PRESS_MS) {
        log.warn("recorder", "record press ignored — the previous one never finished", {
          heldMs,
          recording,
          step: step.current,
        });
      }
      return;
    }
    busy.current = true;
    busySince.current = Date.now();
    step.current = recording ? "stop:begin" : "start:begin";
    setError(undefined);
    // Fires only if the press is still running when it has no business being.
    // Every await below reaches native code or the network, and a press that
    // never comes back holds the guard and kills the button for the rest of the
    // session — so the one fact worth having is WHICH of them it is sitting in.
    // An error rather than a warning: a record button that has stopped working
    // and has not said so is the most expensive state this app has.
    const watchdog = setTimeout(() => {
      log.error("recorder", "record press has not finished", undefined, {
        step: step.current,
        afterMs: STUCK_PRESS_MS,
        wasRecording: recording,
        nativeRecording: services.recorder.isRecording?.() ?? null,
        nativeListening: services.recorder.isListening?.() ?? null,
      });
    }, STUCK_PRESS_MS);
    try {
      await (recording ? stop(cued) : start(cued));
    } catch (failure) {
      // A recording that did not happen is the one loss this app cannot undo,
      // so it is written down whether or not anyone is watching the screen.
      log.error("recorder", recording ? "stop failed" : "start failed", failure);
      setRecording(false);
      // A failed start must not leave the trigger's claim standing, or the
      // recordist's own next capture would be filed as automatic.
      autoTrigger.current = false;
      setError(failure instanceof Error ? failure.message : String(failure));
      if (cued) void services.recorder.playCue?.("failed");
    } finally {
      clearTimeout(watchdog);
      // Closes every press, so the log always has a matching pair. A "record
      // pressed" with no "record press done" after it is the whole diagnosis on
      // its own, and the step says where it stopped.
      log.info("recorder", "record press done", {
        step: step.current,
        ms: Date.now() - busySince.current,
      });
      step.current = "idle";
      busy.current = false;
    }
  }, [recording, services, settlePending, start, stop]);

  // Separate from perform because onPress passes an event object, which would
  // read as cued=true — a tone on every screen tap, from a truthy accident.
  const toggle = useCallback(() => perform(false), [perform]);

  /**
   * Whether a press would actually do anything — the setting holds the
   * session *and* something is in the ears to press. Shown on screen because
   * the trigger is otherwise invisible: armed and not-armed look identical
   * until a tap in the field goes unanswered.
   */
  const [headsetArmed, setHeadsetArmed] = useState(false);
  const triggerOn = services.settings.headsetTrigger;
  useEffect(() => {
    const recorder = services.recorder;
    if (!triggerOn || !recorder.hasBluetoothOutput) {
      setHeadsetArmed(false);
      return;
    }
    let live = true;
    const check = () =>
      void recorder
        .hasBluetoothOutput?.()
        .then((connected) => live && setHeadsetArmed(connected))
        .catch(() => undefined);
    check();
    // AudioDeviceCallback fires for outputs as well, so the AirPods arriving
    // is an "inputs changed" event by a narrower name than it deserves.
    const stop = recorder.onInputsChanged?.(check);
    return () => {
      live = false;
      stop?.();
    };
  }, [services, triggerOn]);

  /**
   * The headset button, routed through the same gate as the screen button.
   *
   * Through perform() and never start/stop directly: the busy ref is what
   * makes a double tap harmless, and the button is easier to double-tap than
   * the screen. Subscribed whenever the recorder can deliver the event — the
   * native side only emits while the trigger setting holds a MediaSession, so
   * the setting gates this without being consulted here.
   */
  /**
   * Subscribed once, through a ref, rather than re-subscribed when `perform`
   * changes identity.
   *
   * `perform` depends on `start`, which depends on `bufferedMs` — and that
   * ticks twice a second for as long as the rolling buffer is open. So this
   * effect was tearing the native listener down and building a new one twice a
   * second, all day, and a press landing in the gap between the two had nothing
   * to arrive at. That is invisible on screen and looks exactly like a button
   * that works sometimes.
   *
   * The ref keeps the handler current without the subscription having a
   * lifetime at all: it is created when the recorder is and lives as long.
   */
  const performRef = useRef(perform);
  performRef.current = perform;
  const recordingRef = useRef(recording);
  recordingRef.current = recording;
  useEffect(
    () =>
      services.recorder.onMediaButton?.(() => {
        // Logged before it is acted on, and it is the only way to tell the two
        // failures apart afterwards: a press that never reached the app at all
        // looks exactly like one that arrived and did nothing. Written with
        // what the recorder was doing at the time, because "the second press
        // does not stop it" is a claim about that state specifically.
        log.info("recorder", "headset press", { recording: recordingRef.current });
        void performRef.current(true);
      }),
    [services],
  );

  /**
   * The microphone session died on its own — revoked mic, dead audio server,
   * full disk. The native side has already ended the session; this is the app
   * catching up so the screen and the service stop claiming otherwise.
   *
   * A death mid-recording goes through the normal stop path, which collects
   * the partial file, writes the capture row, plays the failure tone and says
   * why on screen. A death while only buffering has nothing to collect: the
   * listening state is cleared, the service told to stand down, and the tone
   * played — in the pocket that tone is the entire interface, and a trigger
   * that silently stopped being armed is this feature's worst outcome.
   */
  useEffect(
    () =>
      services.recorder.onSessionFailure?.(({ message, whileRecording }) => {
        log.error("recorder", `microphone session failed: ${message}`, undefined, {
          whileRecording,
          recording: recordingRef.current,
        });
        if (whileRecording && recordingRef.current) {
          void performRef.current(true);
          return;
        }
        setListening(false);
        setBufferedMs(0);
        meterOff();
        setError(`Microphone lost — ${message}`);
        void services.recorder.stopListening?.().catch((failure) =>
          log.warn("recorder", "stopListening failed — the microphone may still be held", failure));
        void services.recorder.playCue?.("failed");
      }),
    [meterOff, services],
  );

  /**
   * The armed hour. The trigger itself runs natively — see IdleTrigger.kt
   * and its mirror in domain/idle.ts — and asks for recordings through
   * onIdle, which drives the same perform() gate as the buttons. This
   * block owns arming, the screen's view of the session, and putting things
   * back the way they were when it ends.
   */
  const [idleArmed, setIdleArmed] = useState(false);
  const [idleDeadline, setIdleDeadline] = useState<number | null>(null);
  const [idleCaptures, setIdleCaptures] = useState(0);
  const [idleEnded, setIdleEnded] =
    useState<IdleControl["endedReason"]>();
  /** Read by the app-leaving listener, which must not close an armed mic. */
  const idleArmedRef = useRef(false);
  idleArmedRef.current = idleArmed;
  /** What arming changed, so disarming can change exactly that back:
   *  "opened" — listening was closed and the session opened it (native closes
   *  it again); "service" — listening was on-screen only and the session took
   *  the foreground service; "nothing" — pocket listening was already on. */
  const idleTook = useRef<"opened" | "service" | "nothing">("nothing");

  const armIdle = useCallback(async () => {
    const recorder = services.recorder;
    if (!recorder.setIdle) return;
    setError(undefined);
    try {
      if (!(await recorder.requestPermission())) {
        setError("Microphone permission denied");
        return;
      }
      // The trigger reads the listening session's PCM, so the buffer comes
      // first — with the service, because an armed hour is exactly the
      // screen-off case. Started here, from the foreground: Android refuses a
      // microphone service started from the background, which is why there is
      // an Arm button and not a seven-o'clock schedule.
      if (!recorder.isListening?.()) {
        await services.refreshMicrophones();
        await recorder.startListening?.({
          input: services.microphoneNow(),
          preRollSeconds: PRE_ROLL_SEC,
          background: true,
        });
        listeningSince.current = Date.now();
        meterOn();
        setListening(true);
        idleTook.current = "opened";
      } else if (!backgroundRef.current) {
        await recorder.setBackground?.(true);
        idleTook.current = "service";
      } else {
        idleTook.current = "nothing";
      }
      const config = idleConfigFrom(services.settings);
      const deadline = Date.now() + config.armSeconds * 1000;
      await recorder.setIdle({
        ...config,
        stopListeningOnDisarm: idleTook.current === "opened",
        untilLabel: `until ${new Date(deadline).toLocaleTimeString([], {
          hour: "numeric",
          minute: "2-digit",
        })}`,
      });
      setIdleDeadline(deadline);
      setIdleCaptures(0);
      setIdleEnded(undefined);
      setIdleArmed(true);
      log.info("recorder", "idle armed", { ...config, took: idleTook.current });
    } catch (failure) {
      log.error("recorder", "could not arm idle mode", failure);
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [meterOn, services]);

  const disarmIdle = useCallback(async () => {
    try {
      // The confirmation arrives as the "disarmed" event, which is also how a
      // session that ends on its own reports — one path, however it ends.
      await services.recorder.setIdle?.(null);
    } catch (failure) {
      log.error("recorder", "could not disarm idle mode", failure);
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [services]);

  useEffect(
    () =>
      services.recorder.onIdle?.((change) => {
        // Logged first, like every other trigger: an event that never arrived
        // and one that arrived and was dropped are different failures, and
        // only the log tells them apart.
        // The meter numbers ride along because a trigger that fired oddly is
        // diagnosed from this line alone, days later, from a synced log —
        // "what did it hear" must not depend on someone having watched the
        // screen at the time.
        const heard = services.recorder.idleState?.();
        log.info("recorder", "idle event", {
          action: change.action,
          reason: change.reason,
          capturesMade: change.capturesMade,
          recording: recordingRef.current,
          bandDb: heard?.bandDb,
          floorDb: heard?.floorDb,
          thresholdDb: heard?.thresholdDb,
        });
        if (change.action === "start") {
          // Already recording: the machine is confused or the press crossed
          // its own re-emission; either way pressing stop here would be worse.
          if (recordingRef.current) return;
          autoTrigger.current = true;
          void performRef.current(false);
          return;
        }
        if (change.action === "stop") {
          if (!recordingRef.current) return;
          void performRef.current(false);
          return;
        }
        setIdleArmed(false);
        setIdleDeadline(null);
        if (change.capturesMade !== undefined) setIdleCaptures(change.capturesMade);
        setIdleEnded(change.reason);
        if (idleTook.current === "opened") {
          // The native side has already closed the microphone and the
          // service — deliberately not left to JS, which may be asleep. The
          // screen catches up here.
          setListening(false);
          setBufferedMs(0);
          meterOff();
        } else if (idleTook.current === "service") {
          // Hand the foreground service back to what the setting says.
          void services.recorder.setBackground?.(backgroundRef.current)
            .catch((failure) =>
              log.warn("recorder", "could not release the service after idle", failure));
        }
        idleTook.current = "nothing";
      }),
    [meterOff, services],
  );

  /**
   * Re-sync from the native session after a trip through the background: the
   * events above may have fired while JS was asleep, and the screen must not
   * claim an armed hour that ended — or miss one still running.
   */
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (next) => {
      if (next !== "active") return;
      const state = services.recorder.idleState?.();
      if (!state || state.phase === "disarmed") {
        if (idleArmedRef.current) {
          setIdleArmed(false);
          setIdleDeadline(null);
        }
        return;
      }
      setIdleArmed(true);
      setIdleDeadline(Date.now() + state.remainingMs);
      setIdleCaptures(state.capturesMade);
    });
    return () => subscription.remove();
  }, [services]);

  return {
    recording, listening, bufferedMs, level, elapsedMs, error, micNote, micLabel,
    notice, headsetArmed, toggle, pending, beginPending, settlePending,
    idle: {
      armed: idleArmed,
      deadline: idleDeadline,
      capturesMade: idleCaptures,
      endedReason: idleEnded,
      arm: armIdle,
      disarm: disarmIdle,
      read: () => services.recorder.idleState?.() ?? null,
    },
    dictation: {
      phase: dictationPhase,
      captureUuid: dictationCapture,
      ringLossMs,
      startedAt: dictationStartedAt.current,
      error: dictationError,
      start: startDictation,
      stop: stopDictation,
    },
  };
}
