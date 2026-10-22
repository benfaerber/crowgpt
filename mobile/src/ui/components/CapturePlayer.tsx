import { useCallback, useEffect, useMemo, useRef } from "react";
import { PanResponder, Pressable, StyleSheet, Text, View } from "react-native";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";

import type { AppServices } from "../../app/AppServices";
import { useNormalized } from "../../playback/useNormalized";
import type { FleetConfig } from "../../domain/config";
import type { DetectedCall } from "../../net/serverTypes";
import { CaptureTimeline } from "./CaptureTimeline";
import { colors, radius, spacing } from "../theme";

function clock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/**
 * Plays a capture back from the phone.
 *
 * Always the local file, never a stream from the server — the recording is on
 * this device whether or not it has ever synced, and a field app should not need
 * a connection to replay what it just recorded.
 */
export function CapturePlayer({
  services,
  config,
  audioPath,
  fallbackMs,
  waveform = [],
  calls = [],
  earLabels = [],
  analyzedDuration,
  crop,
  onCropChange,
  seekRequest,
  onPosition,
}: {
  services: AppServices;
  /** The served vocabulary, for call colours. */
  config: FleetConfig;
  audioPath: string;
  fallbackMs: number;
  waveform?: number[];
  calls?: DetectedCall[];
  /** By-ear marks, banded under the detections on the timeline. */
  earLabels?: { startSec: number; endSec: number; callType: string }[];
  analyzedDuration?: number;
  crop?: { startSec?: number; endSec?: number };
  onCropChange?: (crop: { startSec: number; endSec: number }) => void;
  /** Bumped by the screen to jump playback, e.g. from a Skip to call button. */
  seekRequest?: { seconds: number; nonce: number };
  /**
   * The playhead, reported upward. Marking a call by ear — listen, tap start,
   * tap end — needs the position outside this component, and it is a far better
   * fit on a phone than dragging a handle onto a two-second call. `playing`
   * rides along for the video card, whose picture follows this player.
   */
  onPosition?: (seconds: number, duration: number, playing: boolean) => void;
}) {
  // A field recording peaks around -30 dBFS, which makes reviewing one an
  // exercise in holding the phone against your ear. The louder copy lives in
  // the cache; the recording itself is never touched.
  const boosted = useNormalized(services, audioPath, services.settings.normalizePlayback);
  const player = useAudioPlayer({ uri: boosted.uri });
  const status = useAudioPlayerStatus(player);

  // No cleanup here on purpose: useAudioPlayer already releases the player when
  // the component unmounts, and calling remove() as well double-releases it —
  // "Cannot use shared object that was already released" the moment you leave
  // the screen.

  const duration = status.duration > 0 ? status.duration : fallbackMs / 1000;
  const position = Math.min(status.currentTime, duration);
  const progress = duration > 0 ? position / duration : 0;
  const finished = status.didJustFinish || (duration > 0 && position >= duration - 0.05);

  const toggle = () => {
    if (status.playing) {
      player.pause();
      return;
    }
    // Replaying after the end would otherwise resume from the very end and stop
    // instantly, which reads as a dead button.
    if (finished) void player.seekTo(0);
    player.play();
  };

  // A seek asked for from outside (Skip to call). Keyed on a nonce so asking
  // for the same moment twice still jumps.
  useEffect(() => {
    if (!seekRequest) return;
    void player.seekTo(Math.max(0, seekRequest.seconds));
    player.play();
  }, [seekRequest?.nonce, seekRequest?.seconds, player]);

  useEffect(() => {
    onPosition?.(position, duration, status.playing);
  }, [position, duration, status.playing, onPosition]);

  const barWidth = useRef(0);
  const seekTo = useCallback(
    (x: number, play: boolean) => {
      if (barWidth.current <= 0 || duration <= 0) return;
      const seconds = Math.max(0, Math.min(duration, (x / barWidth.current) * duration));
      void player.seekTo(seconds);
      if (play && !status.playing) player.play();
    },
    [duration, player, status.playing],
  );

  /**
   * Dragging the progress bar.
   *
   * Playback starts on release rather than on the first movement, which is what
   * dragging a scrubber means everywhere else — starting the audio the instant
   * a finger moved would make a careful scrub through a quiet passage
   * impossible to hear.
   */
  const bar = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderTerminationRequest: () => false,
        onPanResponderGrant: (event) => seekTo(event.nativeEvent.locationX, false),
        onPanResponderMove: (event) => seekTo(event.nativeEvent.locationX, false),
        onPanResponderRelease: (event) => seekTo(event.nativeEvent.locationX, true),
      }),
    [seekTo],
  );

  const showTimeline =
    waveform.length > 0 || calls.length > 0 || earLabels.length > 0;

  return (
    <View style={styles.stack}>
      {showTimeline && (
        <CaptureTimeline
          config={config}
          waveform={waveform}
          calls={calls}
          earLabels={earLabels}
          duration={analyzedDuration ?? duration}
          position={position}
          crop={crop}
          onCropChange={onCropChange}
          onScrub={(seconds) => {
            // Follows the finger without committing to playback.
            void player.seekTo(Math.max(0, Math.min(seconds, duration)));
          }}
          onSeek={(seconds) => {
            void player.seekTo(Math.max(0, Math.min(seconds, duration)));
            if (!status.playing) player.play();
          }}
        />
      )}

    <View style={styles.row}>
      <Pressable
        onPress={toggle}
        disabled={!status.isLoaded}
        accessibilityRole="button"
        accessibilityLabel={status.playing ? "Pause" : "Play"}
        style={({ pressed }) => [
          styles.button,
          !status.isLoaded && styles.disabled,
          pressed && styles.pressed,
        ]}
      >
        <Text style={styles.glyph}>{status.playing ? "❚❚" : "▶"}</Text>
      </Pressable>

      <View style={styles.track}>
        {/* Draggable, and it was not before — it had no touch handling at all,
            so the only way to move within a capture was the waveform above.
            Reaching for the progress bar is what everybody tries first. */}
        <View
          onLayout={(event) => {
            barWidth.current = event.nativeEvent.layout.width;
          }}
          {...bar.panHandlers}
          style={styles.barTouch}
        >
          <View style={styles.bar}>
            <View style={[styles.fill, { width: `${Math.round(progress * 100)}%` }]} />
          </View>
          {/* A thumb, because a bar with no handle does not look like something
              you may take hold of. */}
          <View pointerEvents="none" style={[styles.thumb, { left: `${Math.round(progress * 100)}%` }]} />
        </View>
        <Text style={styles.time}>
          {status.isLoaded ? `${clock(position)} / ${clock(duration)}` : "loading…"}
        </Text>
        {/* Said, not hidden. Someone comparing two recordings by ear needs to
            know one of them was turned up 18 dB and the other 4. */}
        {boosted.note ? (
          <Text style={styles.gain} accessibilityLabel={`boosted ${boosted.note}`}>
            {boosted.note}
            {boosted.atCeiling ? " max" : ""}
          </Text>
        ) : null}
      </View>
    </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.sm },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  button: {
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    backgroundColor: colors.accent,
    alignItems: "center",
    justifyContent: "center",
  },
  disabled: { opacity: 0.4 },
  pressed: { opacity: 0.75 },
  glyph: { color: "#fff", fontSize: 16, fontWeight: "700" },
  track: { flex: 1, gap: spacing.xs },
  bar: {
    height: 4,
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    overflow: "hidden",
  },
  fill: { height: 4, backgroundColor: colors.good },
  barTouch: { flex: 1, justifyContent: "center", paddingVertical: 12 },
  thumb: {
    position: "absolute",
    width: 14,
    height: 14,
    borderRadius: 7,
    marginLeft: -7,
    backgroundColor: colors.text,
  },
  gain: { color: colors.textFaint, fontSize: 11, fontVariant: ["tabular-nums"] },
  time: { color: colors.textMuted, fontSize: 12, fontVariant: ["tabular-nums"] },
});
