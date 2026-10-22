import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { FUZZ_MILES_CHOICES, PRECISIONS, type LocationPrecision } from "../../domain/location";
import { REGION_COUNTRIES, RegionPicker } from "./RegionPicker";
import { colors, radius, spacing } from "../theme";

/**
 * How precisely this recordist is willing to say where they were.
 *
 * Three options rather than a switch, because there are genuinely three
 * answers and the middle one is the interesting one: coordinates are wanted for
 * the science and unwanted in a screenshot, and those are not in conflict.
 *
 * The region is asked for rather than looked up. An IP address resolves to
 * wherever the ISP registered the block — this house's own connection claims
 * Idaho from Salt Lake City — and it fails completely behind a VPN. It would
 * also mean telling a third party about every contributor in order to protect
 * them, which is a strange way round. Where there is a GPS fix the phone
 * resolves the region from that instead, and this is the fallback for the
 * person who declined GPS: exactly the person not to guess about.
 */
export function LocationPrecisionPicker({
  precision,
  censor,
  fuzzMiles,
  region,
  onChange,
}: {
  precision: LocationPrecision;
  /** Coordinates recorded but kept off every screen. */
  censor: boolean;
  /** The grid size the fuzzed setting snaps to. */
  fuzzMiles: number;
  region: string;
  onChange: (next: { locationPrecision: LocationPrecision; homeRegion: string;
                     censorCoords: boolean; fuzzMiles: number }) => void;
}) {
  const [draft, setDraft] = useState(region);
  const commit = (next: Partial<{ locationPrecision: LocationPrecision;
                                  homeRegion: string; censorCoords: boolean;
                                  fuzzMiles: number }>) =>
    onChange({ locationPrecision: precision, homeRegion: draft.trim(),
               censorCoords: censor, fuzzMiles, ...next });

  return (
    <View style={styles.group}>
      <Text style={styles.label}>Location precision</Text>

      {PRECISIONS.map((option) => {
        const on = option.key === precision;
        return (
          <Pressable
            key={option.key}
            onPress={() => commit({ locationPrecision: option.key })}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
            style={({ pressed }) => [
              styles.option,
              on && styles.optionOn,
              pressed && styles.pressed,
            ]}
          >
            <Text style={[styles.optionLabel, on && styles.optionLabelOn]}>
              {on ? "● " : "○ "}
              {option.key === "fuzzed" ? `Within ${fuzzMiles} miles` : option.label}
            </Text>
            <Text style={styles.optionDetail}>{option.detail}</Text>
            {option.key === "fuzzed" && on ? (
              <View style={styles.radiusRow}>
                {FUZZ_MILES_CHOICES.map((miles) => (
                  <Pressable
                    key={miles}
                    onPress={() => commit({ fuzzMiles: miles })}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: miles === fuzzMiles }}
                    style={({ pressed }) => [
                      styles.radiusChip,
                      miles === fuzzMiles && styles.radiusChipOn,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text
                      style={[styles.radiusText,
                              miles === fuzzMiles && styles.radiusTextOn]}
                    >
                      {miles} mi
                    </Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
          </Pressable>
        );
      })}

      <Text style={styles.label}>Your region</Text>
      {/* Chosen, not typed. This string is a grouping key — it decides which
          captures count as the same population — and free text turns one place
          into four spellings inside a month. */}
      <RegionPicker
        value={draft}
        onChange={(region) => {
          setDraft(region);
          commit({ homeRegion: region });
        }}
      />
      {precision === "region" && !draft.trim() ? (
        <Text style={styles.warning}>
          Required at this setting — with no coordinates recorded, this is the only
          thing a capture says about where it was. Sync will wait until it is set.
        </Text>
      ) : null}
      <Text style={styles.hint}>
        Used when a capture has no GPS fix of its own. Filled in from your location
        when there is one — never looked up from your internet connection, which
        names your provider&apos;s registration rather than you. Covers{" "}
        {REGION_COUNTRIES}; anywhere else is recorded from the fix itself.
      </Text>

      {precision !== "region" ? (
        <Pressable
          onPress={() => commit({ censorCoords: !censor })}
          accessibilityRole="switch"
          accessibilityState={{ checked: censor }}
          style={({ pressed }) => [styles.censorRow, pressed && styles.pressed]}
        >
          <Text style={[styles.censorTick, censor && styles.censorTickOn]}>
            {censor ? "\u25c9" : "\u25cb"}
          </Text>
          <View style={styles.censorText}>
            <Text style={styles.censorLabel}>Censor coordinates</Text>
            <Text style={styles.hint}>
              Coordinates are still recorded and synced, but every screen shows
              the region instead — this app's own included, so a screenshot
              cannot give away a street.
            </Text>
          </View>
        </Pressable>
      ) : null}

    </View>
  );
}

const styles = StyleSheet.create({
  censorRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  censorTick: { color: colors.textMuted, fontSize: 16, marginTop: 1 },
  censorTickOn: { color: colors.accent },
  censorText: { flex: 1 },
  censorLabel: { color: colors.text, fontSize: 15, fontWeight: "600" },
  group: { gap: spacing.xs },
  label: { color: colors.text, fontSize: 14, fontWeight: "600" },
  hint: { color: colors.textFaint, fontSize: 12 },
  option: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: 2,
  },
  optionOn: { borderColor: colors.accent },
  optionLabel: { color: colors.textMuted, fontSize: 14, fontWeight: "600" },
  optionLabelOn: { color: colors.text },
  optionDetail: { color: colors.textFaint, fontSize: 12 },
  pressed: { opacity: 0.6 },
  radiusRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  radiusChip: {
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
  },
  radiusChipOn: { borderColor: colors.accent },
  radiusText: { color: colors.textMuted, fontSize: 13, fontWeight: "600" },
  radiusTextOn: { color: colors.text },
  warning: { color: colors.warn, fontSize: 12 },
});
