import { describe, expect, it } from "vitest";

import { buildLabelCards, countDecided } from "../../src/domain/labelCards";
import type { DetectedSpan } from "../../src/domain/labelCards";
import type { LabelRecord } from "../../src/domain/labels";

function label(overrides: Partial<LabelRecord> = {}): LabelRecord {
  return {
    uuid: "lab-1",
    captureUuid: "cap-1",
    callType: "call",
    species: "American Crow",
    startSec: 4,
    endSec: 6,
    createdAt: "2026-07-25T18:00:00Z",
    ...overrides,
  };
}

const span = (start: number, end: number, callType?: string): DetectedSpan => ({
  start_sec: start,
  end_sec: end,
  call_type: callType ?? null,
});

describe("building the labelling deck", () => {
  it("makes a card per detection", () => {
    const cards = buildLabelCards([span(4, 6, "call"), span(30, 32)], []);
    expect(cards.map((c) => c.startSec)).toEqual([4, 30]);
    expect(cards[0].predicted).toBe("call");
  });

  it("attaches a decision already made to its detection", () => {
    const cards = buildLabelCards([span(4, 6, "call")], [label()]);
    expect(cards[0].label?.uuid).toBe("lab-1");
  });

  it("gives a span marked by ear its own card", () => {
    const cards = buildLabelCards([], [label({ startSec: 40, endSec: 42 })]);
    expect(cards).toHaveLength(1);
    expect(cards[0].predicted).toBeUndefined();
  });

  it("orders everything by time", () => {
    const cards = buildLabelCards(
      [span(30, 32)],
      [label({ uuid: "early", startSec: 4, endSec: 6 })],
    );
    expect(cards.map((c) => c.startSec)).toEqual([4, 30]);
  });

  it("never lets two detections claim the same decision", () => {
    // The bug this exists to prevent: overlapping detections both matched the
    // one label, so the deck counted 10 decided while only 9 labels existed —
    // and the capture screen, counting labels, disagreed with it.
    const cards = buildLabelCards([span(4, 6, "call"), span(4, 6, "song")], [label()]);
    expect(cards.filter((c) => c.label !== undefined)).toHaveLength(1);
  });

  it("counts decided cards as exactly the number of labels", () => {
    // The two screens agree by construction rather than by counting alike.
    const labels = [
      label({ uuid: "a", startSec: 4, endSec: 6 }),
      label({ uuid: "b", startSec: 30, endSec: 32 }),
      label({ uuid: "c", startSec: 50, endSec: 52 }),
    ];
    const cards = buildLabelCards([span(4, 6), span(4, 6), span(30, 32)], labels);
    expect(countDecided(cards)).toBe(labels.length);
  });

  it("leaves an undecided detection undecided", () => {
    const cards = buildLabelCards([span(4, 6), span(30, 32)], [label()]);
    expect(countDecided(cards)).toBe(1);
  });

  it("treats spans within a hundredth of a second as the same call", () => {
    // Detection spans arrive rounded; an exact match would never fire.
    const cards = buildLabelCards([span(4.001, 6.002)], [label()]);
    expect(cards[0].label?.uuid).toBe("lab-1");
  });

  it("does not match a different call in the same recording", () => {
    // The label is at 4s and the detection at 40s: two separate cards, and the
    // detection is still undecided. Cards come back in time order, so the
    // by-ear label sorts first.
    const cards = buildLabelCards([span(40, 42)], [label()]);
    expect(cards).toHaveLength(2);
    const detection = cards.find((c) => c.startSec === 40);
    expect(detection?.label).toBeUndefined();
  });
});

/**
 * Candidates — detections the analyzer named but was not confident about.
 *
 * They exist to break a loop: the analyzer proposes, the recordist confirms,
 * confirmations become training data, so the corpus could only ever hold calls
 * the model already scored well. The faint ones it most needs were filtered out
 * before anyone saw them.
 */
describe("candidate detections", () => {
  const span = (start: number, candidate: number) => ({
    start_sec: start,
    end_sec: start + 3,
    call_type: "alarm call",
    candidate,
  });

  it("appears in the deck alongside confident detections", () => {
    // Filtering them out here would rebuild the gate one layer up.
    const cards = buildLabelCards([span(3, 0), span(15, 1)], []);
    expect(cards).toHaveLength(2);
  });

  it("is marked, so the card can say the model was unsure", () => {
    const cards = buildLabelCards([span(3, 0), span(15, 1)], []);
    expect(cards.map((c) => c.candidate)).toEqual([false, true]);
  });

  it("still carries the model's guess, hedged rather than hidden", () => {
    // "Maybe an alarm call" is more useful than "unknown" — it tells the
    // labeller what to listen for.
    const [card] = buildLabelCards([span(15, 1)], []);
    expect(card.predicted).toBe("alarm call");
  });

  it("counts as decided once a human rules on it", () => {
    const cards = buildLabelCards([span(15, 1)], [
      {
        uuid: "l1",
        captureUuid: "c1",
        callType: "not_a_crow",
        species: "unknown",
        startSec: 15,
        endSec: 18,
        createdAt: "2026-07-26T09:00:00Z",
      },
    ]);
    expect(cards[0].label?.callType).toBe("not_a_crow");
  });

  it("treats a missing flag as confident, for older servers", () => {
    const [card] = buildLabelCards([{ start_sec: 3, end_sec: 6 }], []);
    expect(card.candidate).toBe(false);
  });

  it("carries the second call the head heard, so it can be marked by ear", () => {
    // Capture 104's shape: an 18-second begging region with an adult cawing
    // over the fledgling. Until the head became one-vs-rest the analyzer took
    // argmax and this span reported begging alone — so the caw was neither
    // shown nor labellable, and the corpus held zero overlapping labels while
    // the field held plenty.
    const [card] = buildLabelCards(
      [
        {
          start_sec: 9,
          end_sec: 27,
          call_type: "begging",
          alternates: [{ call_type: "call", confidence: 0.998 }],
          multi_label: true,
        },
      ],
      [],
    );
    expect(card.predicted).toBe("begging");
    expect(card.alternates).toEqual([{ call_type: "call", confidence: 0.998 }]);
    expect(card.multiLabel).toBe(true);
  });

  it("leaves alternates undefined when the head offered none", () => {
    // "Heard nothing else" and "could not have told you" are different states,
    // and an empty array would render as a prompt with nothing in it.
    const [none] = buildLabelCards([{ start_sec: 0, end_sec: 3, alternates: [] }], []);
    expect(none.alternates).toBeUndefined();
    const [old] = buildLabelCards([{ start_sec: 0, end_sec: 3 }], []);
    expect(old.alternates).toBeUndefined();
    expect(old.multiLabel).toBeUndefined();
  });
});
