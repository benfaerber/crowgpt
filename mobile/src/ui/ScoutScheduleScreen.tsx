import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import {
  daySchedule,
  scoutingAdvice,
  type DayForecast,
  type HourState,
  type ScheduleHour,
} from "../domain/scoutingWindow";
import { colors, pageEnd, radius, spacing } from "./theme";

/**
 * The day as a calendar: one row per forecast hour, tinted by what the
 * hour is worth — the same sun-and-temperature model behind the map
 * header's one-liner, laid out so "when should I go?" is answered by
 * looking instead of by arithmetic on a sunset time.
 */

const ROW_HEIGHT = 44;

const STATES: Record<HourState, { tint: string; text: string; label: string }> = {
  window: { tint: "#153526", text: colors.good, label: "good scouting" },
  quiet: { tint: colors.surface, text: colors.textMuted, label: "quiet" },
  heat: { tint: "#33201c", text: colors.bad, label: "heat lull" },
  night: { tint: colors.surfaceDeep, text: colors.textFaint, label: "night" },
};

const WINDOW_LABELS = {
  morning: "good scouting — morning forage",
  evening: "good scouting — evening commute",
};

const clock = (d: Date) =>
  d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
const hourLabel = (d: Date) =>
  d.toLocaleTimeString(undefined, { hour: "numeric" });

function rowLabel(hour: ScheduleHour): string {
  if (hour.state === "window" && hour.window) {
    return WINDOW_LABELS[hour.window];
  }
  return STATES[hour.state].label;
}

/** A marker line for a sun event that falls inside this hour's row. */
function sunMarker(hour: ScheduleHour, at: Date, label: string) {
  const start = hour.time.getTime();
  if (at.getTime() < start || at.getTime() >= start + 3_600_000) return null;
  const top = ((at.getTime() - start) / 3_600_000) * ROW_HEIGHT;
  return (
    <View key={label} style={[styles.sunLine, { top }]} pointerEvents="none">
      <Text style={styles.sunText}>{label} {clock(at)}</Text>
    </View>
  );
}

export function ScoutScheduleScreen({
  forecast,
  onBack,
}: {
  forecast: DayForecast;
  onBack: () => void;
}) {
  // The now-line moves on its own so a screen left open stays honest.
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(tick);
  }, []);

  const schedule = daySchedule(forecast);
  const advice = scoutingAdvice(forecast, now);

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={({ pressed }) => [pressed && styles.pressed]}>
          <Text style={styles.back}>‹ Map</Text>
        </Pressable>
        <Text style={styles.title}>Today's scouting</Text>
        <Text style={[styles.advice, advice.good && styles.adviceGood]}>
          {advice.good ? "🐦 " : "💤 "}{advice.label}
        </Text>
      </View>
      <ScrollView contentContainerStyle={styles.scroll}>
        {schedule.map((hour) => {
          const state = STATES[hour.state];
          const isNow = now.getTime() >= hour.time.getTime()
            && now.getTime() < hour.time.getTime() + 3_600_000;
          const nowTop = isNow
            ? ((now.getTime() - hour.time.getTime()) / 3_600_000) * ROW_HEIGHT
            : 0;
          return (
            <View key={hour.time.toISOString()} style={styles.row}>
              <Text style={styles.hour}>{hourLabel(hour.time)}</Text>
              <View style={[styles.block, { backgroundColor: state.tint }]}>
                <Text style={[styles.blockLabel, { color: state.text }]}>
                  {rowLabel(hour)}
                </Text>
                <Text style={[styles.temp, { color: state.text }]}>
                  {Math.round(hour.tempC)}°
                </Text>
                {sunMarker(hour, forecast.sunrise, "☀️ sunrise")}
                {sunMarker(hour, forecast.sunset, "🌙 sunset")}
                {isNow ? (
                  <View style={[styles.nowLine, { top: nowTop }]}
                        pointerEvents="none" />
                ) : null}
              </View>
            </View>
          );
        })}
        <Text style={styles.footnote}>
          Sun-anchored, heat-cut at 35 °C — crows keep photoperiod, not wall
          time. Temperatures are Open-Meteo's hourly forecast for where you
          are.
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: 56,
    paddingBottom: spacing.sm,
    gap: 2,
  },
  back: { color: colors.accent, fontSize: 16 },
  pressed: { opacity: 0.6 },
  title: { color: colors.text, fontSize: 18, fontWeight: "700" },
  advice: { color: colors.textFaint, fontSize: 12 },
  adviceGood: { color: colors.good },
  scroll: { paddingHorizontal: spacing.lg, paddingBottom: pageEnd },
  row: { flexDirection: "row", alignItems: "stretch" },
  hour: {
    width: 56,
    color: colors.textFaint,
    fontSize: 11,
    paddingTop: 2,
    textAlign: "right",
    paddingRight: spacing.sm,
  },
  block: {
    flex: 1,
    height: ROW_HEIGHT,
    borderRadius: radius.sm,
    marginBottom: 2,
    paddingHorizontal: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    overflow: "hidden",
  },
  blockLabel: { fontSize: 12, fontWeight: "600" },
  temp: { fontSize: 13, fontVariant: ["tabular-nums"] },
  sunLine: {
    position: "absolute",
    left: 0,
    right: 0,
    borderTopWidth: 1,
    borderTopColor: colors.warn,
    alignItems: "flex-end",
    paddingRight: spacing.sm,
  },
  sunText: { color: colors.warn, fontSize: 10, marginTop: 1 },
  nowLine: {
    position: "absolute",
    left: 0,
    right: 0,
    borderTopWidth: 2,
    borderTopColor: colors.recording,
  },
  footnote: {
    color: colors.textFaint,
    fontSize: 11,
    marginTop: spacing.md,
    lineHeight: 16,
  },
});
