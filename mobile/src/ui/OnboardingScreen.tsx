import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { AppServices, Settings } from "../app/AppServices";
import {
  boldRuns,
  parsePolicy,
  type ConsentAnswers,
  type PolicyBlock,
  type UploadPolicy,
} from "../domain/consent";
import { blockedFromSyncing } from "../domain/location";
import { LocationPrecisionPicker } from "./components/LocationPrecisionPicker";
import { colors, pageEnd, radius, spacing } from "./theme";

type Step = "location" | "uses" | "policy";
const STEPS: Step[] = ["location", "uses", "policy"];

type Answers = { [K in keyof ConsentAnswers]?: boolean };

/**
 * What a new account is walked through after enrolling, before anything syncs.
 *
 * Three steps: how precisely to say where recordings were made, the two uses a
 * recordist may refuse, and the policy itself. Both consent questions start
 * unanswered: publishing is opt-in, and a preselected "yes" for the generator
 * would be the same thing with better manners.
 */
export function OnboardingScreen({
  services,
  onChange,
  onDone,
  onSkip,
}: {
  services: AppServices;
  onChange: (settings: Settings) => void;
  onDone: () => void;
  /** Leave for now; omitted when reached from Settings, where Back does it. */
  onSkip?: () => void;
}) {
  const [step, setStep] = useState<Step>("location");
  const existing = services.identity;
  const [answers, setAnswers] = useState<Answers>({
    allowGenerator: existing?.allowGenerator,
    allowPublish: existing?.allowPublish,
  });
  const [policy, setPolicy] = useState<UploadPolicy | undefined>();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | undefined>();

  const loadPolicy = () => {
    setLoading(true);
    void services.uploadPolicy().then((fetched) => {
      setPolicy(fetched);
      setLoading(false);
    });
  };
  useEffect(loadPolicy, [services]);

  const index = STEPS.indexOf(step);
  const locationProblem = blockedFromSyncing(services.settings);
  const answered = answers.allowGenerator !== undefined && answers.allowPublish !== undefined;

  const accept = async () => {
    if (!policy || !answered) return;
    setBusy(true);
    setMessage(undefined);
    try {
      await services.giveConsent(policy.version, answers as ConsentAnswers);
      onDone();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Text style={styles.progress}>Step {index + 1} of {STEPS.length}</Text>

        {step === "location" && (
          <>
            <Text style={styles.title}>Where you record</Text>
            <Text style={styles.lede}>
              Recordings are only useful with a place attached, but you choose how
              precise it is. You can change this later in Settings.
            </Text>
            <LocationPrecisionPicker
              precision={services.settings.locationPrecision}
              censor={services.settings.censorCoords}
              fuzzMiles={services.settings.fuzzMiles}
              region={services.settings.homeRegion}
              onChange={(next) => onChange({ ...services.settings, ...next })}
            />
          </>
        )}

        {step === "uses" && (
          <>
            <Text style={styles.title}>What your recordings are for</Text>
            <Text style={styles.lede}>
              Everything you upload helps build CawDex, a catalogue of crow calls,
              and Crow Translate, which pairs calls with what was happening. Two
              more uses are up to you.
            </Text>
            <Choice
              title="The generator"
              detail="A model that learns to produce new crow calls."
              value={answers.allowGenerator}
              yes="Allow"
              no="Don't allow"
              onChange={(allowGenerator) => setAnswers({ ...answers, allowGenerator })}
            />
            <Choice
              title="A public dataset, one day"
              detail="CrowGPT is open source. If a dataset is ever released, only recordings from people who opted in are included, at your location precision, never with spoken notes."
              value={answers.allowPublish}
              yes="Opt in"
              no="Keep private"
              onChange={(allowPublish) => setAnswers({ ...answers, allowPublish })}
            />
          </>
        )}

        {step === "policy" && (
          <>
            {loading && <ActivityIndicator color={colors.accent} />}
            {!loading && policy && <PolicyText blocks={parsePolicy(policy.text)} />}
            {!loading && !policy && (
              <View style={styles.group}>
                <Text style={styles.title}>Can&apos;t load the policy</Text>
                <Text style={styles.lede}>
                  The server didn&apos;t answer. You can record offline; nothing
                  syncs until you have read and accepted this.
                </Text>
                <Button label="Try again" onPress={loadPolicy} />
              </View>
            )}
          </>
        )}

        {message ? <Text style={styles.message}>{message}</Text> : null}

        <View style={styles.nav}>
          {index > 0 && <Button label="Back" onPress={() => setStep(STEPS[index - 1])} />}
          {step === "location" && (
            <Button
              label="Next"
              primary
              disabled={Boolean(locationProblem)}
              onPress={() => setStep("uses")}
            />
          )}
          {step === "uses" && (
            <Button label="Next" primary disabled={!answered} onPress={() => setStep("policy")} />
          )}
          {step === "policy" && (
            <Button
              label={busy ? "Saving…" : "I agree"}
              primary
              disabled={busy || !policy}
              onPress={() => void accept()}
            />
          )}
        </View>
        {step === "location" && locationProblem ? (
          <Text style={styles.hint}>Choose your region to continue.</Text>
        ) : null}
        {onSkip ? (
          <Pressable onPress={onSkip} style={({ pressed }) => [pressed && styles.pressed]}>
            <Text style={styles.skip}>Not now — record offline, nothing syncs until this is done</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </View>
  );
}

function Choice({
  title,
  detail,
  value,
  yes,
  no,
  onChange,
}: {
  title: string;
  detail: string;
  value?: boolean;
  yes: string;
  no: string;
  onChange: (value: boolean) => void;
}) {
  return (
    <View style={styles.choice}>
      <Text style={styles.label}>{title}</Text>
      <Text style={styles.hint}>{detail}</Text>
      <View style={styles.choiceRow}>
        {([[true, yes], [false, no]] as const).map(([option, label]) => (
          <Pressable
            key={label}
            onPress={() => onChange(option)}
            accessibilityRole="radio"
            accessibilityState={{ selected: value === option }}
            style={({ pressed }) => [
              styles.option,
              value === option && styles.optionOn,
              pressed && styles.pressed,
            ]}
          >
            <Text style={[styles.optionText, value === option && styles.optionTextOn]}>{label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function PolicyText({ blocks }: { blocks: PolicyBlock[] }) {
  return (
    <View style={styles.group}>
      {blocks.map((block, i) => {
        if (block.kind === "heading") {
          return (
            <Text key={i} style={block.level === 1 ? styles.title : styles.heading}>
              {block.text}
            </Text>
          );
        }
        const runs = boldRuns(block.text).map((run, j) => (
          <Text key={j} style={run.bold ? styles.bold : undefined}>{run.text}</Text>
        ));
        if (block.kind === "bullet") {
          return (
            <View key={i} style={styles.bulletRow}>
              <Text style={styles.prose}>{block.ordinal ? `${block.ordinal}.` : "•"}</Text>
              <Text style={[styles.prose, styles.bulletText]}>{runs}</Text>
            </View>
          );
        }
        return <Text key={i} style={styles.prose}>{runs}</Text>;
      })}
    </View>
  );
}

function Button({
  label,
  onPress,
  primary,
  disabled,
}: {
  label: string;
  onPress: () => void;
  primary?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.action,
        primary && styles.actionPrimary,
        disabled && styles.disabled,
        pressed && styles.pressed,
      ]}
    >
      <Text style={styles.actionText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  body: { paddingHorizontal: spacing.lg, paddingTop: 56, paddingBottom: pageEnd, gap: spacing.lg },
  progress: { color: colors.textFaint, fontSize: 12, fontWeight: "600" },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  heading: { color: colors.text, fontSize: 17, fontWeight: "700", marginTop: spacing.sm },
  lede: { color: colors.textMuted, fontSize: 14 },
  group: { gap: spacing.sm },
  label: { color: colors.text, fontSize: 15, fontWeight: "600" },
  hint: { color: colors.textFaint, fontSize: 12 },
  prose: { color: colors.textMuted, fontSize: 14, lineHeight: 20 },
  bold: { color: colors.text, fontWeight: "700" },
  bulletRow: { flexDirection: "row", gap: spacing.sm },
  bulletText: { flex: 1 },
  choice: {
    gap: spacing.xs,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  choiceRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  option: {
    flex: 1,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  optionOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  optionText: { color: colors.textMuted, fontSize: 14, fontWeight: "600" },
  optionTextOn: { color: "#fff" },
  message: { color: colors.textMuted, fontSize: 13 },
  skip: { color: colors.textMuted, fontSize: 13, textAlign: "center" },
  nav: { flexDirection: "row", gap: spacing.sm },
  action: {
    flex: 1,
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  actionPrimary: { backgroundColor: colors.accent },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.6 },
  actionText: { color: "#fff", fontSize: 14, fontWeight: "700" },
});
