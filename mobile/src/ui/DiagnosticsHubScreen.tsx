import { StatusBar } from "expo-status-bar";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, pageEnd, radius, spacing } from "./theme";
import { useRememberedScroll } from "./useRememberedScroll";

/**
 * One door to everything that answers "why did that not work".
 *
 * These pages arrived one per field failure and hung off Settings individually,
 * which is how the third one got lost among the sync buttons and the fourth was
 * nearly written as a fifth entry in the same list. They belong together: each
 * one takes a symptom nobody can reproduce on a desk and turns it into a fact.
 *
 * Ordered by how often the failure has actually happened, not by subsystem.
 */

type Page = {
  title: string;
  /** The symptom, in the words somebody would use in the field. */
  symptom: string;
  open: () => void;
};

export function DiagnosticsHubScreen({
  onBack,
  onOpenMicSources,
  onOpenHeadset,
  onOpenCues,
  onOpenLogs,
}: {
  onBack: () => void;
  onOpenMicSources: () => void;
  onOpenHeadset: () => void;
  onOpenCues: () => void;
  onOpenLogs: () => void;
}) {
  const scroll = useRememberedScroll("diagnostics");
  const pages: Page[] = [
    {
      title: "Audio cues",
      symptom: "A tone, a heartbeat or the spoken warning that nobody heard.",
      open: onOpenCues,
    },
    {
      title: "Earbud button",
      symptom: "A press in the field that did nothing, with no way to say whether it arrived.",
      open: onOpenHeadset,
    },
    {
      title: "Microphone sources",
      symptom: "Which source the OS actually gave us, and what it did to the audio.",
      open: onOpenMicSources,
    },
    {
      title: "App log",
      symptom: "Everything this phone wrote down, including what it did while the screen was off.",
      open: onOpenLogs,
    },
  ];

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <ScrollView {...scroll} contentContainerStyle={styles.content}>
        <Pressable onPress={onBack} accessibilityRole="button">
          <Text style={styles.back}>‹ Settings</Text>
        </Pressable>
        <Text style={styles.title}>Diagnostics</Text>
        <Text style={styles.intro}>
          Each of these exists because something failed in the field and there was
          no way afterwards to say which half of it had. They report rather than
          fix: what the phone did, and what it thought it was doing.
        </Text>

        {pages.map((page) => (
          <Pressable
            key={page.title}
            onPress={page.open}
            style={({ pressed }) => [styles.card, pressed && styles.pressed]}
          >
            <Text style={styles.cardTitle}>{page.title}</Text>
            <Text style={styles.cardBody}>{page.symptom}</Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingTop: 64, gap: spacing.md, paddingBottom: pageEnd },
  title: { color: colors.text, fontSize: 22, fontWeight: "700" },
  back: { color: colors.accent, fontSize: 16 },
  intro: { color: colors.textMuted, fontSize: 13, lineHeight: 19 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
  },
  pressed: { opacity: 0.75 },
  cardTitle: { color: colors.text, fontSize: 16, fontWeight: "700" },
  cardBody: { color: colors.textMuted, fontSize: 13, lineHeight: 18 },
});
