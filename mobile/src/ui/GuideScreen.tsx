import { useMemo } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { AppServices } from "../app/AppServices";
import { colors, radius, spacing , pageEnd} from "./theme";
import { useRememberedScroll } from "./useRememberedScroll";

const PART_TITLES: Record<string, string> = {
  using: "Using the app",
  birds: "Reading the birds",
};

/**
 * The field guide.
 *
 * Every word comes from the server. Nothing here is written into the app,
 * because what counts as a good recording is still being worked out — the
 * answer to "should I record this?" has already changed twice — and these
 * phones belong to volunteers. There is no update to schedule and no way to ask
 * a dozen people to reinstall.
 *
 * Which means this screen can be empty, on a phone that has never reached the
 * server. It says so plainly rather than rendering nothing: an empty screen
 * reads as a broken app, and the recordist is the one person who cannot tell
 * the difference.
 */
export function GuideScreen({
  services,
  onBack,
}: {
  services: AppServices;
  onBack: () => void;
}) {
  const scroll = useRememberedScroll("guide");
  const parts = useMemo(() => {
    const sections = services.config.guide ?? [];
    const order: string[] = [];
    const byPart = new Map<string, typeof sections>();
    for (const section of sections) {
      if (!byPart.has(section.part)) {
        byPart.set(section.part, []);
        order.push(section.part);
      }
      byPart.get(section.part)!.push(section);
    }
    return order.map((part) => ({ part, sections: byPart.get(part)! }));
  }, [services.config.guide]);

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12}>
          <Text style={styles.back}>‹ Back</Text>
        </Pressable>
        <Text style={styles.title}>Field guide</Text>
      </View>

      <ScrollView {...scroll} contentContainerStyle={styles.body}>
        {parts.length === 0 ? (
          <Text style={styles.empty}>
            The guide is kept on the server so it can be improved without
            reinstalling the app. This phone has not fetched it yet — sync once
            and it will be here.
          </Text>
        ) : (
          parts.map(({ part, sections }) => (
            <View key={part} style={styles.part}>
              <Text style={styles.partTitle}>{PART_TITLES[part] ?? part}</Text>
              {sections.map((section) => (
                <View key={section.key} style={styles.card}>
                  <Text style={styles.sectionTitle}>{section.title}</Text>
                  <Text style={styles.sectionBody}>{section.body}</Text>
                </View>
              ))}
            </View>
          ))
        )}
        <Text style={styles.footer}>
          Something here wrong or missing? Say so — the guide is meant to be
          argued with, and it is one edit on the server to fix.
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingTop: 56, gap: spacing.xs },
  back: { color: colors.accent, fontSize: 16 },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  body: { padding: spacing.lg, gap: spacing.lg, paddingBottom: pageEnd},
  part: { gap: spacing.sm },
  partTitle: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
  },
  sectionTitle: { color: colors.text, fontSize: 16, fontWeight: "700" },
  // Roomy on purpose: this is the one screen in the app somebody reads rather
  // than scans, often outdoors and often one-handed.
  sectionBody: { color: colors.textMuted, fontSize: 14, lineHeight: 21 },
  empty: { color: colors.textFaint, fontSize: 13, lineHeight: 20 },
  footer: { color: colors.textFaint, fontSize: 12, lineHeight: 18 },
});
