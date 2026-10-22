import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Dimensions,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type { AppServices } from "../app/AppServices";
import { useAnalysis } from "../app/useAnalysis";
import { useNormalized } from "../playback/useNormalized";
import { buildLabelCards, countDecided, type LabelCard } from "../domain/labelCards";
import { newClientUuid } from "../domain/ids";
import type { LabelRecord } from "../domain/labels";
import type { CaptureRecord } from "../domain/types";
import { deviceRandomBytes } from "../platform/random";
import { useKeyboardInset } from "./useKeyboardInset";
import { CallCard } from "./components/CallCard";
import { KeyboardAwareScroll } from "./components/KeyboardAwareScroll";
import { SightingLogger } from "./components/SightingLogger";
import { SilenceMark } from "./components/SilenceMark";
import { colors, pageEnd, spacing } from "./theme";

/** A second of lead-in — landing on the onset clips the start of the call. */
const LEAD_IN_SEC = 1;

/**
 * Labelling, one call at a time.
 *
 * The list this replaces asked you to hold a whole capture in your head: every
 * call, its span, what you had already decided, all scrolling past at once. But
 * the task is not "review a capture" — it is "decide about this call, then the
 * next one". So it is a deck: one card, the audio for that call and nothing
 * else, swipe when done.
 *
 * Playback is scoped to the card. Hearing the call you are labelling should not
 * mean scrubbing a two-minute recording to find it again.
 */
export function LabelingScreen({
  services,
  capture,
  onBack,
}: {
  services: AppServices;
  capture: CaptureRecord;
  onBack: () => void;
}) {
  const analysis = useAnalysis(services, capture);
  const [labels, setLabels] = useState<LabelRecord[]>([]);
  // The silence mark lives here rather than on the capture screen: "there are no
  // calls in this" is a labelling decision, and this is the labelling screen.
  const [record, setRecord] = useState(capture);
  const keyboardInset = useKeyboardInset();
  const [index, setIndex] = useState(0);
  const deck = useRef<ScrollView | null>(null);
  const width = Dimensions.get("window").width;

  // The screen where quiet calls are judged, so the boosted copy matters most
  // here. Nothing stored changes — see playback/NormalizedWav.ts.
  const boosted = useNormalized(services, capture.audioPath, services.settings.normalizePlayback);
  const player = useAudioPlayer({ uri: boosted.uri });
  const status = useAudioPlayerStatus(player);
  const playingUntil = useRef<number | undefined>(undefined);

  const refresh = useCallback(async () => {
    setLabels(await services.labels.forCapture(capture.uuid));
  }, [capture.uuid, services]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Stop at the end of the call rather than running on into the next one. The
  // player has no notion of a span, so the boundary is enforced here.
  useEffect(() => {
    if (playingUntil.current === undefined) return;
    if (status.currentTime >= playingUntil.current) {
      player.pause();
      playingUntil.current = undefined;
    }
  }, [status.currentTime, player]);

  const cards = buildLabelCards(analysis.calls, labels);
  const current = cards[Math.min(index, Math.max(0, cards.length - 1))];

  const playCard = (card: LabelCard) => {
    if (status.playing) {
      player.pause();
      playingUntil.current = undefined;
      return;
    }
    playingUntil.current = card.endSec + 0.2;
    void player.seekTo(Math.max(0, card.startSec - LEAD_IN_SEC));
    player.play();
  };

  const decide = async (card: LabelCard, callType: string) => {
    if (card.label) await services.removeLabel(card.label);
    await services.addLabel({
      uuid: newClientUuid(deviceRandomBytes),
      captureUuid: capture.uuid,
      callType,
      startSec: card.startSec,
      endSec: card.endSec,
      fromDetection: card.predicted !== undefined,
    });
    await refresh();
    // Deliberately does not move on. The context tagger only appears once a
    // call has a label, so advancing here revealed it and took it away in the
    // same instant — the tags that say what was happening while the bird called
    // were unreachable for exactly as long as they existed.
    //
    // Deciding a call is now two steps, not one: what it was, then what was
    // going on around it. Swiping is the recordist's, and the footer says so.
  };

  const retract = async (card: LabelCard) => {
    if (!card.label) return;
    await services.removeLabel(card.label);
    await refresh();
  };

  if (cards.length === 0) {
    return (
      <View style={styles.screen}>
        <Header onBack={onBack} title="Label calls" subtitle="" />
        <KeyboardAwareScroll contentContainerStyle={styles.emptyBody}>
          <Text style={styles.emptyText}>
            {analysis.calls.length === 0 && capture.syncState !== "synced"
              ? "Sync this capture and the analyzer will propose calls to work through."
              : "The analyzer found nothing here. Mark calls by ear on the capture screen — those are the examples it most needs."}
          </Text>

          {/* "Nothing was said" is a labelling decision too, and this is the
              screen you are on when you reach it. It also gets the full width
              here, rather than a card nested inside another card. */}
          <SilenceMark
            services={services}
            captureUuid={record.uuid}
            silentConfirmedAt={record.silentConfirmedAt}
            hasLabels={labels.length > 0}
            onChange={async (silent) =>
              setRecord(
                await services.repository.update(record.uuid, {
                  silentConfirmedAt: silent ? new Date().toISOString() : undefined,
                }),
              )
            }
          />

          <SightingLogger services={services} captureUuid={record.uuid} />
        </KeyboardAwareScroll>
      </View>
    );
  }

  const decided = countDecided(cards);

  return (
    // Padding rather than a scroll view: the deck is flex:1, so shrinking the
    // screen by the keyboard's height makes the deck give up the space and
    // everything below it — including the sighting logger — rises clear.
    <View style={[styles.screen, { paddingBottom: keyboardInset }]}>
      <Header
        onBack={onBack}
        title={`${index + 1} of ${cards.length}`}
        subtitle={`${decided} decided`}
      />

      {/* One segment per call, filled when decided. A deck shows you one thing
          at a time, which is the point — but it also hides how much is left and
          which ones you skipped, and that was the first thing to go wrong with
          it. Tapping jumps. */}
      <View style={styles.strip}>
        {cards.map((card, i) => (
          <Pressable
            key={card.key}
            onPress={() => {
              player.pause();
              playingUntil.current = undefined;
              setIndex(i);
              deck.current?.scrollTo({ x: i * width, animated: true });
            }}
            style={styles.segmentTouch}
          >
            <View
              style={[
                styles.segment,
                // Undecided candidates read as amber in the strip, so the
                // maybes are visible before you swipe into them.
                card.candidate && card.label === undefined && styles.segmentUnsure,
                card.label !== undefined && styles.segmentDone,
                i === index && styles.segmentCurrent,
              ]}
            />
          </Pressable>
        ))}
      </View>

      {/* A ScrollView rather than a FlatList: a capture has a handful of calls,
          so there is nothing to virtualize, and paging is a ScrollView prop that
          FlatList's types do not inherit. */}
      <ScrollView
        ref={deck}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={(event: NativeSyntheticEvent<NativeScrollEvent>) => {
          const next = Math.round(event.nativeEvent.contentOffset.x / width);
          if (next !== index) {
            // Stop the previous call rather than letting it play under the next
            // card, which sounds like the new card is wrong.
            player.pause();
            playingUntil.current = undefined;
            setIndex(next);
          }
        }}
      >
        {cards.map((item) => (
          <ScrollView
            key={item.key}
            style={{ width }}
            contentContainerStyle={styles.card}
            showsVerticalScrollIndicator={false}
          >
            <CallCard
              services={services}
              captureUuid={capture.uuid}
              card={item}
              playing={status.playing && item.key === current?.key}
              onPlay={() => playCard(item)}
              onDecide={(callType) => void decide(item, callType)}
              onRetract={() => void retract(item)}
              onChanged={refresh}
            />
          </ScrollView>
        ))}
      </ScrollView>

      <Text style={styles.swipeHint}>
        {index < cards.length - 1
          ? "Tag what was happening, then swipe for the next call"
          : "Last call"}
      </Text>

      {/* Below the deck rather than inside it: a sighting is about the whole
          recording, not about the call currently on screen — putting it on a
          card would imply otherwise. Collapsed until tapped, so it costs the
          deck nothing. */}
      <View style={styles.footer}>
        <SightingLogger services={services} captureUuid={record.uuid} />
      </View>
    </View>
  );
}

function Header({
  onBack,
  title,
  subtitle,
}: {
  onBack: () => void;
  title: string;
  subtitle: string;
}) {
  return (
    <View style={styles.header}>
      <Pressable onPress={onBack} style={({ pressed }) => [pressed && styles.pressed]}>
        <Text style={styles.back}>‹ Done</Text>
      </Pressable>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.subtitle}>{subtitle}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingTop: 56,
    paddingBottom: spacing.sm,
  },
  back: { color: colors.accent, fontSize: 16 },
  title: { color: colors.text, fontSize: 16, fontWeight: "700", flex: 1, textAlign: "center" },
  subtitle: { color: colors.textFaint, fontSize: 12 },
  card: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl, gap: spacing.sm },
  strip: {
    flexDirection: "row",
    gap: 3,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  segmentTouch: { flex: 1, paddingVertical: spacing.xs },
  segment: { height: 4, borderRadius: 2, backgroundColor: colors.border },
  segmentUnsure: { backgroundColor: colors.warn, opacity: 0.55 },
  segmentDone: { backgroundColor: colors.good },
  segmentCurrent: { height: 6, borderRadius: 3, backgroundColor: colors.accent },
  swipeHint: {
    color: colors.textFaint,
    fontSize: 12,
    textAlign: "center",
    paddingBottom: spacing.lg,
  },
  emptyBody: { padding: spacing.lg, gap: spacing.lg, paddingBottom: pageEnd },
  footer: { paddingHorizontal: spacing.lg, paddingBottom: spacing.lg },
  emptyText: { color: colors.textFaint, fontSize: 14, textAlign: "center" },
  pressed: { opacity: 0.7 },
});
