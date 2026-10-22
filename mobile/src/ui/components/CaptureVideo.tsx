import { useEffect, useRef } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { useEvent } from "expo";
import { useVideoPlayer, VideoView } from "expo-video";

import { log } from "../../app/Log";
import { followPicture, videoOffsetSec } from "../../domain/videoFollow";
import { colors, formatBytes, formatDuration, radius, spacing } from "../theme";

/**
 * Plays back the silent video shot alongside a capture.
 *
 * Silent by construction, not by accident — the camera records muted so the
 * microphone stays with `raw-audio`. The sound for this moment is the capture's
 * own WAV, played by the audio player above; this is the picture only.
 *
 * The two files have different pasts: the WAV reaches back through the rolling
 * buffer, the camera starts at the press. So the picture FOLLOWS the audio
 * player, offset by that pre-roll — playing the sound brings the picture along
 * at the right moment instead of fifteen seconds late. While the audio is
 * paused the picture is yours to scrub freely; see domain/videoFollow.
 */
export function CaptureVideo({
  uri,
  bytes,
  preRollSec,
  audioDurationSec,
  seekRequest,
  follow,
}: {
  uri: string;
  bytes?: number;
  /** The capture's measured pre-roll — absent on captures made before it was stamped. */
  preRollSec?: number;
  /** For the fallback offset when preRollSec was never recorded. */
  audioDurationSec?: number;
  /** Same seek the audio gets, so Skip to call moves both. */
  seekRequest?: { seconds: number; nonce: number };
  /** The audio playhead this picture stays in step with. */
  follow?: { seconds: number; playing: boolean };
}) {
  const source = { uri: uri.startsWith("file://") ? uri : `file://${uri}` };
  const player = useVideoPlayer(source);
  /**
   * The player's word on itself, not an assumption. The first version had an
   * error branch nothing could ever reach — no listener set it — so a player
   * that failed to open (the camera can still be releasing the codec seconds
   * after a recording) sat as a silent black box with nothing to say and
   * nothing to press. Leaving and coming back was the only repair.
   */
  const playerState = useEvent(player, "statusChange", { status: player.status });
  const offsetSec = videoOffsetSec(preRollSec, audioDurationSec, player.duration || 0);

  useEffect(() => {
    if (playerState.status !== "error") return;
    log.warn("video", "the player could not open the file", {
      error: String(playerState.error?.message ?? playerState.error ?? "unknown"),
    });
  }, [playerState.status, playerState.error]);

  useEffect(() => {
    if (!seekRequest) return;
    // The request arrives in the audio's timeline; the picture starts
    // offsetSec into it.
    player.currentTime = Math.max(0, seekRequest.seconds - offsetSec);
    // Deliberately not offsetSec itself: a re-render moving the offset (the
    // video's duration finishing loading) must not replay an old seek.
  }, [seekRequest?.nonce, seekRequest?.seconds, player]);

  // Only the transition into pause may stop the picture — see PictureFollow.
  const audioWasPlaying = useRef(false);
  useEffect(() => {
    if (!follow) return;
    const audioJustPaused = audioWasPlaying.current && !follow.playing;
    audioWasPlaying.current = follow.playing;
    const action = followPicture({
      audioSec: follow.seconds,
      audioPlaying: follow.playing,
      audioJustPaused,
      offsetSec,
      videoSec: player.currentTime,
      videoPlaying: player.playing,
      videoDurationSec: player.duration || 0,
    });
    if (action.seekTo !== undefined) player.currentTime = action.seekTo;
    if (action.play === true) player.play();
    if (action.play === false) player.pause();
  }, [follow?.seconds, follow?.playing, player, offsetSec]);

  const skip = (by: number) => {
    player.currentTime = Math.max(0, player.currentTime + by);
  };

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>Video</Text>
        <Text style={styles.meta}>
          {bytes ? formatBytes(bytes) : ""} · silent
        </Text>
      </View>

      {playerState.status === "error" ? (
        <View style={[styles.video, styles.videoNotice]}>
          <Text style={styles.error}>
            The video would not open — the camera may still be letting go of it.
          </Text>
          <Pressable
            onPress={() => player.replace(source)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.retry, pressed && styles.pressed]}
          >
            <Text style={styles.retryText}>Try again</Text>
          </Pressable>
        </View>
      ) : (
        <View>
          <VideoView
            style={styles.video}
            player={player}
            nativeControls
            contentFit="contain"
          />
          {playerState.status === "loading" ? (
            <View style={[StyleSheet.absoluteFill, styles.videoNotice]}>
              <ActivityIndicator size="small" color={colors.textMuted} />
              <Text style={styles.meta}>Loading the video…</Text>
            </View>
          ) : null}
        </View>
      )}

      {/* Said, because otherwise it reads as a broken file: the sound reaches
          back through the rolling buffer and the camera does not. */}
      {offsetSec > 0.05 ? (
        <Text style={styles.hint}>
          The first {offsetSec.toFixed(0)}s of sound come from before the
          camera started — the picture joins in when the audio reaches{" "}
          {formatDuration(offsetSec * 1000)}.
        </Text>
      ) : null}

      {/* Native controls cover scrubbing, but a crow call is a second long and
          dragging a thumb that far is fiddly — these step precisely. */}
      <View style={styles.skips}>
        {[-10, -5, -1, 1, 5, 10].map((by) => (
          <Pressable
            key={by}
            onPress={() => skip(by)}
            style={({ pressed }) => [styles.skip, pressed && styles.pressed]}
          >
            <Text style={styles.skipText}>{by > 0 ? `+${by}s` : `${by}s`}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { color: colors.text, fontSize: 16, fontWeight: "700" },
  meta: { color: colors.textMuted, fontSize: 12 },
  video: {
    width: "100%",
    aspectRatio: 16 / 9,
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
  },
  error: { color: colors.bad, fontSize: 12, textAlign: "center" },
  hint: { color: colors.textFaint, fontSize: 11 },
  videoNotice: {
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    padding: spacing.md,
  },
  retry: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
  },
  retryText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  skips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  skip: {
    flex: 1,
    minWidth: 44,
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  skipText: { color: colors.text, fontSize: 12, fontWeight: "600", fontVariant: ["tabular-nums"] },
  pressed: { opacity: 0.7 },
});
