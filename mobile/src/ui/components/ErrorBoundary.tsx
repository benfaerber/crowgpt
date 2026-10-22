import { Component, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { log } from "../../app/Log";
import { colors, radius, spacing } from "../theme";

interface Props {
  children: ReactNode;
}

interface State {
  failure?: Error;
  /** React's own trace: which components were mounting, not which functions ran. */
  where?: string;
}

/**
 * A screen that throws while rendering should not take the app with it.
 *
 * The global error handler catches everything that throws in an event handler
 * or a promise, but a throw during render is different: React unmounts the
 * whole tree, and what the recordist sees is a black screen with no way back —
 * indistinguishable from the app being broken, in a park, holding a phone.
 *
 * So the tree gets a floor. It logs the failure with the component stack, which
 * is the part that says *where*, and offers the one action that reliably helps:
 * go back to the list, which remounts everything below it.
 *
 * Deliberately a class. Error boundaries are the one thing hooks cannot express.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = {};

  static getDerivedStateFromError(failure: Error): State {
    return { failure };
  }

  componentDidCatch(failure: Error, info: { componentStack?: string | null }) {
    log.error("ui", "render failed", failure, {
      componentStack: info.componentStack?.slice(0, 2000),
    });
    // Pushed down now rather than on the timer: whatever broke the render may
    // well take the process next, and this is the entry that would explain it.
    void log.flush();
    this.setState({ where: info.componentStack ?? undefined });
  }

  render() {
    const { failure } = this.state;
    if (!failure) return this.props.children;

    return (
      <View style={styles.screen}>
        <Text style={styles.title}>That screen broke</Text>
        <Text style={styles.body}>
          The recording itself is safe — captures live in the phone&apos;s database and
          nothing here touched them.
        </Text>
        <Text style={styles.detail} selectable>
          {failure.name}: {failure.message}
        </Text>
        <Text style={styles.hint}>
          Written to the app log with the full trace. Settings › App log, and it goes
          up with the next sync.
        </Text>
        <Pressable
          onPress={() => this.setState({ failure: undefined, where: undefined })}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>Try again</Text>
        </Pressable>
      </View>
    );
  }
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
    padding: spacing.lg,
    paddingTop: 96,
    gap: spacing.md,
  },
  title: { color: colors.text, fontSize: 22, fontWeight: "700" },
  body: { color: colors.textMuted, fontSize: 14 },
  detail: {
    color: colors.bad,
    fontFamily: "monospace",
    fontSize: 12,
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    padding: spacing.md,
  },
  hint: { color: colors.textFaint, fontSize: 12 },
  action: {
    backgroundColor: colors.accent,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  actionText: { color: colors.text, fontSize: 16, fontWeight: "700" },
  pressed: { opacity: 0.7 },
});
