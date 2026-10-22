import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  BackHandler,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { File } from "expo-file-system";

import type { AppServices } from "../app/AppServices";
import { useRecorderView } from "../app/RecorderContext";
import { newClientUuid } from "../domain/ids";
import { stickyCaptureDefaults } from "../domain/settings";
import type { NewCapture } from "../domain/types";
import { deviceRandomBytes } from "../platform/random";
import { FIX_TIMEOUT_MS } from "../recording/LocationProvider";
import { withTimeout } from "../domain/timeout";
import { colors, radius, spacing } from "./theme";

/**
 * What the screen is waiting for, in the recordist's terms.
 *
 * Each names the step actually running rather than the press that started it.
 * The location one says how long it is willing to wait, because that is the
 * step that takes seconds and the question it has to answer is "is this stuck
 * or is it working" — a wait with a known end is the difference.
 */
const STAGE_TEXT = {
  finalizing: "Finishing the video file…",
  locating: "Waiting for a location fix…",
  writing: "Saving the capture…",
} as const;

const STAGE_HINT = {
  finalizing: "The camera has to close the file before it can be kept.",
  locating: `Started when you pressed Record. Gives up after ${Math.round(
    FIX_TIMEOUT_MS / 1000,
  )}s and keeps the capture without one.`,
  writing: "",
} as const;

/**
 * Films a capture while `raw-audio` records the sound.
 *
 * The camera runs **muted** on purpose. Its own track would be compressed and
 * speech-processed — fine to watch, useless to train on — and it would also take
 * the microphone, which `raw-audio` needs for the 48 kHz signal the model
 * actually learns from. Muting frees the mic and keeps the two streams at their
 * best: a pristine WAV, and video for context.
 *
 * The two are separate files rather than one muxed mp4, which also means a sync
 * over a bad link delivers the audio first and the bulky video after.
 */
export function VideoCaptureScreen({
  services,
  onBack,
  onCaptured,
}: {
  services: AppServices;
  onBack: () => void;
  onCaptured: () => void;
}) {
  const [permission, requestPermission] = useCameraPermissions();
  // From the provider above the routes, so the placeholder this screen puts up
  // survives the screen itself — it has to still be there once the list is back.
  const recorder = useRecorderView();
  // The stages after Stop are not cosmetic and they are not one thing.
  //
  // 'finalizing' is load-bearing: recordAsync only resolves on the camera's
  // Finalize event, so the view has to stay mounted until then or the file is
  // lost. The screen therefore refuses to leave until the promise settles.
  //
  // 'locating' is the one that made this look broken. The GPS fix is started
  // when Record is pressed, so a four-second clip stops long before a fix
  // arrives and the capture then waits up to FIX_TIMEOUT_MS for one. That is
  // the several seconds between Stop and the capture appearing in the list, and
  // for the whole of it the screen used to say "Saving video…" — naming a step
  // that had already finished, over a disabled button, which reads as frozen
  // rather than as working.
  const [phase, setPhase] =
    useState<"idle" | "recording" | "finalizing" | "locating" | "writing">("idle");
  const recording = phase === "recording";
  // The stage, or nothing when the screen is idle or filming. Derived rather
  // than a second boolean so there is one answer to "is it working" and the
  // label cannot be asked for when there is no step running.
  const stage = phase === "idle" || phase === "recording" ? undefined : phase;
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | undefined>();
  const [videoFailed, setVideoFailed] = useState(false);
  // 0..1 of the device's range; the native side maps it onto 1x..maxZoomRatio.
  // The real ratio is never exposed to JS, so this is shown as a proportion
  // rather than a made-up multiplier.
  const [zoom, setZoom] = useState(0);
  const zoomAtPinchStart = useRef(0);
  const pinchStartSpread = useRef(0);
  const camera = useRef<CameraView>(null);
  const startedAt = useRef(0);
  // The placeholder this take is standing behind, from the moment the files are
  // safe until the row exists. A ref, not state: this screen unmounts the
  // instant it hands the recordist back to the list, and the work that settles
  // it carries on afterwards.
  const placeholder = useRef<string | undefined>(undefined);
  const fix = useRef<ReturnType<AppServices["location"]["current"]> | null>(null);

  useEffect(() => {
    if (!recording) return;
    const timer = setInterval(() => setElapsedMs(Date.now() - startedAt.current), 250);
    return () => clearInterval(timer);
  }, [recording]);

  const start = useCallback(async () => {
    setError(undefined);
    if (!(await services.recorder.requestPermission())) {
      setError("Microphone permission denied");
      return;
    }
    try {
      // Audio first: it is the part that matters, so if the camera fails we
      // still know before anything was written.
      await services.recorder.start();
      fix.current = services.location.current();
      startedAt.current = Date.now();
      setElapsedMs(0);
      setPhase("recording");

      const view = camera.current;
      if (!view) throw new Error("camera not ready");

      // Resolves only when stopRecording() is called. Muting is a CameraView
      // prop, not an option here — see the `mute` prop below.
      const video = await view.recordAsync();

      const audio = await services.recorder.stop();
      // Stamped the moment the file closes, not after the awaits below. The
      // location wait sits between here and the capture object, so reading the
      // clock down there dated every recording by however long the fix took —
      // nothing at all outdoors with a fix in hand, up to FIX_TIMEOUT_MS
      // indoors, which is the worst kind of error: silent and variable.
      const endedAt = Date.now();

      // Saying so and going idle are separate: the message is true now, but
      // there is still a capture to write, and an idle screen re-enables Back
      // over work that is still running — the same hole the 'saving' phase was
      // added to close.
      if (!video?.uri) setVideoFailed(true);

      // BOTH FILES ARE CLOSED AND SAFE, which is the moment the camera stops
      // being needed. Everything below is a location lookup and a database
      // write, and none of it wants a viewfinder — so the recordist goes back
      // to the list now and watches a placeholder become the capture, instead
      // of watching a dead preview for the length of a GPS fix.
      //
      // Not one line earlier: recordAsync resolves on the camera's Finalize
      // event, and leaving before that loses the recording outright. That is
      // what the 'finalizing' phase is for and it is still the rule.
      if (video?.uri) {
        placeholder.current = recorder.beginPending("video", audio.durationMs);
        onCaptured();
      }

      setPhase("locating");
      // Bounded here as well as inside the provider, for the reason
      // useRecorder.stop gives: a promise from outside this file carries no
      // guarantee it ever settles, and this one is awaited before the capture
      // is written.
      const pending = fix.current;
      fix.current = null;
      const where = await withTimeout(
        pending ?? Promise.resolve(undefined),
        FIX_TIMEOUT_MS,
        undefined,
      );
      setPhase("writing");

      const capture: NewCapture = {
        uuid: newClientUuid(deviceRandomBytes),
        mediaUuid: newClientUuid(deviceRandomBytes),
        recordedAt: new Date(endedAt - audio.durationMs).toISOString(),
        durationMs: audio.durationMs,
        sampleRate: audio.sampleRate,
        channels: audio.channels,
        audioPath: audio.path,
        bytes: audio.bytes,
        latitude: where?.latitude,
        longitude: where?.longitude,
        // The measured drain of the ring — how many seconds of sound precede
        // the picture. Playback aligns the two players with it; without it the
        // caw arrives fifteen seconds before the crow does.
        preRollSec: audio.preRollSec,
        videoPath: video?.uri,
        videoBytes: video?.uri ? new File(video.uri).size : undefined,
        videoMediaUuid: video?.uri ? newClientUuid(deviceRandomBytes) : undefined,
        videoUploadedBytes: 0,
        ...stickyCaptureDefaults(services.settings),
      };
      await services.repository.add(capture);
      // Idle only once the row exists. On the video-failed path this screen
      // stays put to show why, and it must not look ready for another take
      // while the last one is still being written.
      setPhase("idle");
    } catch (failure) {
      if (services.recorder.isRecording()) await services.recorder.stop();
      setPhase("idle");
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      // Whatever happened, the spinner goes. A placeholder left standing over a
      // capture that failed to write is a "Loading…" that never resolves, which
      // is a worse thing to leave on screen than the gap it was closing.
      if (placeholder.current) {
        recorder.settlePending(placeholder.current);
        placeholder.current = undefined;
      }
    }
  }, [onCaptured, recorder, services]);

  const pinch = useMemo(() => {
    const spread = (touches: { pageX: number; pageY: number }[]) =>
      Math.hypot(touches[0].pageX - touches[1].pageX, touches[0].pageY - touches[1].pageY);

    return PanResponder.create({
      onStartShouldSetPanResponder: (event) => event.nativeEvent.touches.length === 2,
      onMoveShouldSetPanResponder: (event) => event.nativeEvent.touches.length === 2,
      onPanResponderGrant: (event) => {
        const touches = event.nativeEvent.touches;
        if (touches.length !== 2) return;
        pinchStartSpread.current = spread(touches);
        setZoom((current) => {
          zoomAtPinchStart.current = current;
          return current;
        });
      },
      onPanResponderMove: (event) => {
        const touches = event.nativeEvent.touches;
        if (touches.length !== 2 || pinchStartSpread.current === 0) return;
        // Half a screen-width of spread covers the whole range, which is roughly
        // the sensitivity of the stock camera app.
        const change = spread(touches) / pinchStartSpread.current - 1;
        setZoom(Math.min(1, Math.max(0, zoomAtPinchStart.current + change * 0.6)));
      },
    });
  }, []);

  const nudgeZoom = useCallback((by: number) => {
    setZoom((current) => Math.min(1, Math.max(0, current + by)));
  }, []);

  const stop = useCallback(() => {
    // Ends recordAsync above, which resolves on Finalize and writes the capture.
    setPhase("finalizing");
    camera.current?.stopRecording();
  }, []);

  // Leaving mid-recording would strand the microphone held by raw-audio, since
  // the stop below only runs once recordAsync resolves.
  useEffect(
    () => () => {
      if (services.recorder.isRecording()) void services.recorder.stop();
    },
    [services],
  );

  // Back must not tear the camera down while a file is being finalized.
  useEffect(() => {
    if (phase === "idle") return;
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => true);
    return () => subscription.remove();
  }, [phase]);

  if (!permission) return <View style={styles.screen} />;

  if (!permission.granted) {
    return (
      <View style={[styles.screen, styles.centered]}>
        <Text style={styles.title}>Camera access needed</Text>
        <Text style={styles.hint}>
          Video is optional — audio-only recording works without it.
        </Text>
        <Pressable
          onPress={requestPermission}
          style={({ pressed }) => [styles.action, styles.actionPrimary, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>Allow camera</Text>
        </Pressable>
        <Pressable onPress={onBack} style={({ pressed }) => [pressed && styles.pressed]}>
          <Text style={styles.back}>Back</Text>
        </Pressable>
      </View>
    );
  }

  const seconds = Math.floor(elapsedMs / 1000);
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <View style={styles.screen}>
      <CameraView
        ref={camera}
        style={styles.preview}
        mode="video"
        facing="back"
        mute
        zoom={zoom}
      />
      {/* Sits over the preview but under the controls, so a pinch anywhere on
          the picture zooms while the buttons stay tappable. */}
      <View style={styles.pinchLayer} {...pinch.panHandlers} pointerEvents="box-only" />

      {/* Over the whole picture rather than inside the shutter, which is where
          it was and is why this looked frozen: a small grey label at the foot
          of a black preview is indistinguishable from a dead button. It also
          swallows the taps a stopped-looking screen invites. */}
      {stage ? (
        <View style={styles.waitLayer}>
          <View style={styles.waitCard}>
            <ActivityIndicator size="large" color="#fff" />
            <Text style={styles.waitText}>{STAGE_TEXT[stage]}</Text>
            {STAGE_HINT[stage] ? (
              <Text style={styles.waitHint}>{STAGE_HINT[stage]}</Text>
            ) : null}
            <Text style={styles.waitHint}>Keep this screen open.</Text>
          </View>
        </View>
      ) : null}

      <View style={styles.overlay}>
        <View style={styles.topRow}>
          <Pressable onPress={onBack} disabled={phase !== "idle"}>
            <Text style={[styles.back, phase !== "idle" && styles.disabledText]}>‹ Captures</Text>
          </Pressable>
          {recording ? <Text style={styles.clock}>● {clock}</Text> : null}
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}
        {videoFailed ? (
          <Text style={styles.error}>
            The camera returned no file. The audio was saved as a normal capture.
          </Text>
        ) : null}

        <View style={styles.bottom}>
          <View style={styles.zoomRow}>
            <Pressable
              onPress={() => nudgeZoom(-0.1)}
              disabled={zoom <= 0}
              style={({ pressed }) => [styles.zoomKey, zoom <= 0 && styles.disabledText, pressed && styles.pressed]}
            >
              <Text style={styles.zoomKeyText}>−</Text>
            </Pressable>

            <View style={styles.zoomTrack}>
              <View style={[styles.zoomFill, { width: `${Math.round(zoom * 100)}%` }]} />
            </View>

            <Pressable
              onPress={() => nudgeZoom(0.1)}
              disabled={zoom >= 1}
              style={({ pressed }) => [styles.zoomKey, zoom >= 1 && styles.disabledText, pressed && styles.pressed]}
            >
              <Text style={styles.zoomKeyText}>+</Text>
            </Pressable>

            <Text style={styles.zoomLabel}>
              {zoom === 0 ? "wide" : `${Math.round(zoom * 100)}%`}
            </Text>
          </View>

          <Text style={styles.note}>
            Audio is recorded separately at full quality; the video is silent.
          </Text>
          <Pressable
            onPress={recording ? stop : start}
            disabled={stage !== undefined}
            style={({ pressed }) => [
              styles.shutter,
              recording && styles.shutterRecording,
              stage && styles.shutterSaving,
              pressed && styles.pressed,
            ]}
          >
            {stage ? (
              <View style={styles.savingRow}>
                <ActivityIndicator size="small" color="#fff" />
                <Text style={styles.shutterText}>{STAGE_TEXT[stage]}</Text>
              </View>
            ) : (
              <Text style={styles.shutterText}>{recording ? "Stop" : "Record video"}</Text>
            )}
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#000" },
  centered: { alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.lg },
  preview: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  pinchLayer: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  waitLayer: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(0,0,0,0.6)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
  },
  waitCard: {
    backgroundColor: "rgba(0,0,0,0.75)",
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.sm,
    alignItems: "center",
    maxWidth: 320,
  },
  waitText: { color: "#fff", fontSize: 16, fontWeight: "700", textAlign: "center" },
  waitHint: { color: "rgba(255,255,255,0.7)", fontSize: 12, textAlign: "center" },
  overlay: { flex: 1, justifyContent: "space-between", padding: spacing.lg, paddingTop: 56 },
  topRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  back: { color: "#fff", fontSize: 16, textShadowColor: "#000", textShadowRadius: 6 },
  disabledText: { opacity: 0.4 },
  clock: {
    color: "#fff",
    fontSize: 15,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
    textShadowColor: "#000",
    textShadowRadius: 6,
  },
  bottom: { gap: spacing.sm },
  zoomRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  zoomKey: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "rgba(0,0,0,0.45)",
    alignItems: "center",
    justifyContent: "center",
  },
  zoomKeyText: { color: "#fff", fontSize: 22, fontWeight: "700", lineHeight: 26 },
  zoomTrack: {
    flex: 1,
    height: 4,
    borderRadius: 2,
    backgroundColor: "rgba(255,255,255,0.3)",
    overflow: "hidden",
  },
  zoomFill: { height: 4, backgroundColor: "#fff" },
  zoomLabel: {
    color: "#fff",
    fontSize: 12,
    minWidth: 44,
    textAlign: "right",
    fontVariant: ["tabular-nums"],
    textShadowColor: "#000",
    textShadowRadius: 6,
  },
  note: {
    color: "#fff",
    fontSize: 12,
    textAlign: "center",
    textShadowColor: "#000",
    textShadowRadius: 6,
  },
  shutter: {
    backgroundColor: colors.accent,
    paddingVertical: 20,
    borderRadius: radius.md,
    alignItems: "center",
  },
  shutterRecording: { backgroundColor: colors.recording },
  shutterSaving: { backgroundColor: colors.border },
  savingRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  shutterText: { color: "#fff", fontSize: 18, fontWeight: "700" },
  pressed: { opacity: 0.75 },
  title: { color: colors.text, fontSize: 18, fontWeight: "700" },
  hint: { color: colors.textMuted, fontSize: 13, textAlign: "center" },
  error: { color: colors.bad, fontSize: 13, textAlign: "center" },
  action: {
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
  },
  actionPrimary: { backgroundColor: colors.accent },
  actionText: { color: "#fff", fontSize: 14, fontWeight: "700" },
});
