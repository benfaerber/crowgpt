import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import type { SyncEstimate } from "../../app/syncEta";
import { formatDurationShort, formatRate } from "../../app/syncEta";
import { colors, formatBytes, radius, spacing } from "../theme";

/**
 * The standing answer to "what is still only on this phone?".
 *
 * Sync is manual by design, which only stays safe if the backlog is impossible
 * to miss — so the count is always on screen, not hidden behind a menu.
 */
export function SyncBar({
  pendingCount,
  syncing,
  lastMessage,
  warning,
  progress,
  onSync,
  onCancel,
}: {
  pendingCount: number;
  syncing: boolean;
  lastMessage?: string;
  /** The server is behind this app and may be dropping fields it doesn't know. */
  warning?: string;
  progress?: SyncEstimate;
  onSync: () => void;
  onCancel: () => void;
}) {
  // Sync is no longer only a push. It checks the server's wire version, sends
  // the app's own log, and pulls the analysis down — none of which a phone with
  // everything uploaded could ask for, because the one control meaning "talk to
  // the server" refused exactly when there was nothing to send. That is also
  // why warming the analysis had to move to app launch.
  const nothingPending = pendingCount === 0;

  return (
    <View style={styles.wrapper}>
      {/* Above the bar, not inside the status line: the status line is one row
          that gets truncated, and this is the message that must not be. */}
      {warning ? <Text style={styles.warning}>{warning}</Text> : null}
      <View style={styles.bar}>
        <View style={styles.status}>
          <Text style={styles.count}>
            {syncing && progress
              ? `Syncing ${progress.captureIndex} of ${progress.captureCount}`
              : nothingPending
                ? "All captures synced"
                : `${pendingCount} waiting to sync`}
          </Text>

          {syncing && progress ? (
            <>
              <View style={styles.track}>
                <View style={[styles.fill, { width: `${Math.round(progress.fraction * 100)}%` }]} />
              </View>
              <Text style={styles.message}>
                {formatBytes(progress.bytesSent)} of {formatBytes(progress.bytesToSend)}
                {progress.secondsLeft !== undefined
                  ? ` · ${formatDurationShort(progress.secondsLeft)} left`
                  : " · estimating…"}
                {progress.bytesPerSecond !== undefined
                  ? ` · ${formatRate(progress.bytesPerSecond)}`
                  : ""}
              </Text>
            </>
          ) : lastMessage ? (
            <Text numberOfLines={1} style={styles.message}>
              {lastMessage}
            </Text>
          ) : null}
        </View>

        {syncing ? (
          <Pressable onPress={onCancel} style={({ pressed }) => [styles.action, pressed && styles.pressed]}>
            <ActivityIndicator size="small" color={colors.text} />
            <Text style={styles.actionText}>Stop</Text>
          </Pressable>
        ) : (
          <Pressable
            onPress={onSync}
            style={({ pressed }) => [
              styles.action,
              styles.actionPrimary,
              // Not dimmed at all any more. It was greyed to say "nothing to
              // upload", but it now checks the server, pushes the log and pulls
              // the analysis whatever the queue looks like — so a faded button
              // was describing a refusal that no longer happens.
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.actionText}>Sync</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: spacing.xs },
  warning: {
    color: colors.warn,
    fontSize: 11,
    borderWidth: 1,
    borderColor: colors.warn,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  bar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  status: { flex: 1, gap: 2 },
  count: { color: colors.text, fontSize: 14, fontWeight: "600" },
  track: {
    height: 4,
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    overflow: "hidden",
    marginTop: 4,
  },
  fill: { height: 4, backgroundColor: colors.accent },
  message: { color: colors.textMuted, fontSize: 11 },
  action: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.border,
  },
  actionPrimary: { backgroundColor: colors.accent },
  pressed: { opacity: 0.75 },
  actionText: { color: "#fff", fontSize: 14, fontWeight: "700" },
});
