import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AppServices } from "../../app/AppServices";
import { colorForCall, labelText } from "../../domain/config";
import type { LabelCard } from "../../domain/labelCards";
import { CallerPicker } from "./CallerPicker";
import { ContextTagger } from "./ContextTagger";
import { ReferenceExamples } from "./ReferenceExamples";
import { colors, radius, spacing } from "../theme";

/**
 * One call, one question. The card the labelling deck deals.
 *
 * Everything on it is scoped to a single detected (or hand-marked) span: the
 * audio button, the analyzer's reading of it, the call-type choices, and — once
 * a label exists — the caller and context questions that only make sense
 * attached to a decided call.
 */
export function CallCard({
  services,
  captureUuid,
  card,
  playing,
  onPlay,
  onDecide,
  onRetract,
  onChanged,
}: {
  services: AppServices;
  captureUuid: string;
  card: LabelCard;
  playing: boolean;
  onPlay: () => void;
  onDecide: (callType: string) => void;
  onRetract: () => void;
  onChanged: () => void;
}) {
  const config = services.config;
  const chosen = card.label?.callType;
  const [compareTo, setComparing] = useState<string | undefined>();

  return (
    <>
      <Text style={styles.span}>
        {card.startSec.toFixed(1)}–{card.endSec.toFixed(1)}s ·{" "}
        {(card.endSec - card.startSec).toFixed(1)}s
      </Text>

      <Pressable
        onPress={onPlay}
        style={({ pressed }) => [styles.play, pressed && styles.pressed]}
      >
        <Text style={styles.playText}>{playing ? "⏸  Stop" : "▶  Play this call"}</Text>
      </Pressable>
      <Text style={styles.hint}>
        Starts a second early — a call is easier to place with the moment before it.
      </Text>

      {/* An uncertain detection says so plainly. Dressing it up as a confident
          guess would make a coin-flip look like ground truth, and this deck is
          where ground truth gets made. */}
      {card.candidate ? (
        <Text style={styles.unsure}>
          Analyzer wasn&apos;t sure — maybe{" "}
          <Text style={{ fontWeight: "700" }}>
            {card.predicted ? labelText(config, card.predicted) : "a crow"}
          </Text>
          , maybe nothing. Worth a listen: quiet calls are the ones it needs most.
        </Text>
      ) : card.predicted ? (
        <Text style={styles.guess}>
          Analyzer heard{" "}
          <Text style={{ color: colorForCall(config, card.predicted), fontWeight: "700" }}>
            {labelText(config, card.predicted)}
          </Text>
        </Text>
      ) : (
        <Text style={styles.guess}>Marked by ear — no analyzer guess</Text>
      )}

      {/* The second call in the span. This is a prompt, not a suggestion to
          pick between: the card still asks one question and takes one answer,
          because a label IS one call. What it adds is the reason to go back to
          the capture screen and mark the other one by ear — the only route a
          concurrent call has ever taken into this corpus, and one nobody takes
          unless told there is something to take it for. */}
      {card.alternates?.length ? (
        <Text style={styles.alternates}>
          {card.multiLabel ? "It also heard " : "It was torn with "}
          {card.alternates.map((alt, i) => (
            <Text key={alt.call_type}>
              {i > 0 ? ", " : ""}
              <Text
                style={{
                  color: colorForCall(config, alt.call_type),
                  fontWeight: "700",
                }}
              >
                {labelText(config, alt.call_type)}
              </Text>
            </Text>
          ))}
          {card.multiLabel
            ? " in this span. If two birds overlap here, answer for the one you"
              + " picked and mark the other by ear on the capture screen."
            : " — one call, two readings of it."}
        </Text>
      ) : null}

      <View style={styles.questionRow}>
        <Text style={styles.question}>What was it?</Text>
        {/* One tap to hear what the same call type sounded like last time.
            Consistency across a season is the hard part of hand-labelling, and
            nobody holds a fortnight of decisions in their head. */}
        {chosen || card.predicted ? (
          <Pressable
            onPress={() => setComparing(compareTo ? undefined : (chosen ?? card.predicted))}
            accessibilityRole="button"
            style={({ pressed }) => [pressed && styles.pressed]}
          >
            <Text style={styles.compare}>
              {compareTo ? "Hide examples" : "Compare with mine"}
            </Text>
          </Pressable>
        ) : null}
      </View>

      {compareTo ? (
        <ReferenceExamples
          services={services}
          config={config}
          callType={compareTo}
          onClose={() => setComparing(undefined)}
        />
      ) : null}

      <View style={styles.choices}>
        {config.labels.map((def) => {
          const active = chosen === def.key;
          return (
            <Pressable
              key={def.key}
              onPress={() => onDecide(def.key)}
              style={({ pressed }) => [
                styles.choice,
                { borderColor: colorForCall(config, def.key) },
                active && { backgroundColor: `${colorForCall(config, def.key)}33` },
                pressed && styles.pressed,
              ]}
            >
              <Text style={[styles.choiceText, active && styles.choiceTextOn]}>
                {active ? "✓ " : ""}
                {def.text}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {card.label ? (
        <>
          <CallerPicker
            services={services}
            label={card.label}
            onChanged={onChanged}
          />
          <ContextTagger
            services={services}
            captureUuid={captureUuid}
            labelUuid={card.label.uuid}
            startSec={card.label.startSec}
            endSec={card.label.endSec}
            onChanged={onChanged}
          />
          <Pressable
            onPress={onRetract}
            style={({ pressed }) => [styles.retract, pressed && styles.pressed]}
          >
            <Text style={styles.retractText}>Retract this label</Text>
          </Pressable>
        </>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  span: {
    color: colors.textMuted,
    fontSize: 13,
    fontVariant: ["tabular-nums"],
    textAlign: "center",
  },
  play: {
    backgroundColor: colors.accent,
    borderRadius: radius.md,
    paddingVertical: spacing.lg,
    alignItems: "center",
  },
  playText: { color: "#fff", fontSize: 17, fontWeight: "700" },
  hint: { color: colors.textFaint, fontSize: 11, textAlign: "center" },
  unsure: { color: colors.warn, fontSize: 13, textAlign: "center" },
  guess: { color: colors.textMuted, fontSize: 14, textAlign: "center", marginTop: spacing.sm },
  // Smaller than the guess and directly under it: a second call is real
  // information but it is not the question being asked, and giving it equal
  // weight would read as "pick one of these two".
  alternates: {
    color: colors.textMuted,
    fontSize: 12,
    textAlign: "center",
    marginTop: spacing.xs,
    lineHeight: 17,
  },
  questionRow: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  compare: { color: colors.accent, fontSize: 12, fontWeight: "600" },
  question: { color: colors.text, fontSize: 14, fontWeight: "600", marginTop: spacing.sm },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  choice: {
    borderWidth: 2,
    borderRadius: radius.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  choiceText: { color: colors.text, fontSize: 14, fontWeight: "600" },
  choiceTextOn: { fontWeight: "800" },
  retract: { alignItems: "center", paddingVertical: spacing.sm },
  retractText: { color: colors.bad, fontSize: 12 },
  pressed: { opacity: 0.7 },
});
