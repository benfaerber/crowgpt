import { beforeEach, describe, expect, it } from "vitest";
import { webcrypto } from "node:crypto";

import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import { MemoryContextRepository } from "../../src/data/MemoryContextRepository";
import { MemoryFamilyRepository } from "../../src/data/MemoryFamilyRepository";
import { MemoryLabelRepository } from "../../src/data/MemoryLabelRepository";
import { MemoryDictationRepository } from "../../src/data/MemoryDictationRepository";
import { MemorySightingRepository } from "../../src/data/MemorySightingRepository";
import {
  blockedFromSyncing,
  coordsToSend,
  describePlace,
  displayCoords,
  formatRegion,
  fuzzedCoords,
  mayShowCoords,
  wantsFix,
  type LocationPrecision,
} from "../../src/domain/location";
import { newClientUuid } from "../../src/domain/ids";
import type { NewCapture } from "../../src/domain/types";
import { FieldServerClient } from "../../src/net/FieldServerClient";
import { MemoryMediaSource } from "../../src/sync/MediaSource";
import { SyncEngine } from "../../src/sync/SyncEngine";
import { FakeFieldServer } from "../FakeFieldServer";

const randomBytes = (length: number) => webcrypto.getRandomValues(new Uint8Array(length));
const AUDIO = new Uint8Array(2048).fill(7);

/** Haversine, in miles — how far the snap actually moved a point. */
function milesBetween(
  a: { latitude: number; longitude: number },
  b: { latitude: number; longitude: number },
): number {
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const h =
    Math.sin(rad(b.latitude - a.latitude) / 2) ** 2
    + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude))
      * Math.sin(rad(b.longitude - a.longitude) / 2) ** 2;
  return 2 * 3958.8 * Math.asin(Math.sqrt(h));
}

/**
 * How precisely a recordist says where they were.
 *
 * The promise is kept on the phone, which is the only place it can be kept: a
 * rule the server applies is something a contributor has to trust, and a rule
 * the phone applies is something they can verify by watching what leaves.
 */
describe("what may be shown", () => {
  it("shows coordinates only at exact", () => {
    expect(mayShowCoords("exact", false)).toBe(true);
    expect(mayShowCoords("region")).toBe(false);
  });

  it("stops asking for a fix when there is nothing to do with one", () => {
    // The cheapest way to keep a promise about coordinates is to never have any.
    expect(wantsFix("region")).toBe(false);
    expect(wantsFix("exact")).toBe(true);
  });

  const capture = { latitude: 40.7460, longitude: -111.8747, region: "Utah, US" };

  it("prints coordinates at exact", () => {
    expect(describePlace(capture, "exact", false)).toBe("40.7460, -111.8747");
  });

  it("prints the region on a phone whose screenshots must be safe", () => {
    // The app's own screens included: a promo image of the capture list would
    // otherwise give away a street.
    expect(describePlace(capture, "exact", true)).toBe("Utah, US");
    expect(describePlace(capture, "region")).toBe("Utah, US");
  });

  it("says nothing rather than guessing when there is no region", () => {
    expect(describePlace({ latitude: 1, longitude: 2 }, "region")).toBeUndefined();
  });
});

describe("snapping to a grid — the middle setting", () => {
  // A grid rather than jitter, because jitter fails exactly the person it
  // protects: fifty captures at home, each displaced independently, average
  // straight back to the house.
  const home = { latitude: 40.7460, longitude: -111.8747 };

  it("moves the point, but never further than the radius", () => {
    const snapped = fuzzedCoords(home.latitude, home.longitude, 5);
    expect(snapped).not.toEqual(home);
    expect(milesBetween(home, snapped)).toBeLessThanOrEqual(5);
  });

  it("is idempotent, so the server's backstop never moves it twice", () => {
    const once = fuzzedCoords(home.latitude, home.longitude, 5);
    expect(fuzzedCoords(once.latitude, once.longitude, 5)).toEqual(once);
  });

  it("sends neighbours to the same point — repetition reveals nothing", () => {
    const here = fuzzedCoords(home.latitude, home.longitude, 5);
    const there = fuzzedCoords(home.latitude + 0.001, home.longitude + 0.001, 5);
    expect(there).toEqual(here);
  });

  it("honours a tighter radius with a finer grid", () => {
    expect(milesBetween(home, fuzzedCoords(home.latitude, home.longitude, 1)))
      .toBeLessThanOrEqual(1);
  });

  it("still asks for a fix — there are coordinates to record", () => {
    expect(wantsFix("fuzzed")).toBe(true);
  });

  it("shows the snapped point, and only under an explicit censor-off", () => {
    expect(mayShowCoords("fuzzed", false)).toBe(true);
    expect(mayShowCoords("fuzzed", true)).toBe(false);
    expect(mayShowCoords("fuzzed", undefined)).toBe(false);
  });

  it("never hands a screen the raw fix", () => {
    const shown = displayCoords(home, "fuzzed", false, 5);
    expect(shown).toEqual(fuzzedCoords(home.latitude, home.longitude, 5));
  });

  it("prints the snapped point marked as approximate", () => {
    const place = describePlace({ ...home, region: "Utah, US" }, "fuzzed", false, 5);
    expect(place).toMatch(/^≈ /);
    expect(place).not.toContain("40.7460");
  });

  it("sends the snapped point, not the fix", () => {
    const sent = coordsToSend(home, "fuzzed", 5);
    expect(sent).toEqual(fuzzedCoords(home.latitude, home.longitude, 5));
  });

  it("never blocks a sync — there is always something recorded", () => {
    expect(blockedFromSyncing({ locationPrecision: "fuzzed", homeRegion: "" }))
      .toBeUndefined();
  });
});

describe("naming a region", () => {
  it("is region and country, nothing finer", () => {
    // A city is already too small in a rural area — "Alta, US" is a village of
    // four hundred people.
    expect(formatRegion({ region: "Utah", isoCountryCode: "US" })).toBe("Utah, US");
  });

  it("handles the contributor who is not in the US", () => {
    expect(formatRegion({ region: "Nordrhein-Westfalen", isoCountryCode: "DE" }))
      .toBe("Nordrhein-Westfalen, DE");
  });

  it("falls back to the country when the region is unknown", () => {
    expect(formatRegion({ country: "Germany" })).toBe("Germany");
  });

  it("is undefined rather than empty when nothing is known", () => {
    expect(formatRegion({})).toBeUndefined();
  });
});

describe("what leaves the phone", () => {
  it("withholds coordinates entirely at region precision", () => {
    expect(coordsToSend({ latitude: 40.7, longitude: -111.8 }, "region")).toEqual({});
  });

  it("sends them at exact even when censored, which is about showing rather than keeping", () => {
    // These captures are still wanted for territory work. They are simply not
    // for display.
    expect(coordsToSend({ latitude: 40.7, longitude: -111.8 }, "exact"))
      .toEqual({ latitude: 40.7, longitude: -111.8 });
  });
});

describe("syncing without a region", () => {
  it("waits at region precision, where nothing else says where a capture was", () => {
    // A corpus of recordings that name no place at all is one where the
    // population cannot be identified afterwards.
    expect(blockedFromSyncing({ locationPrecision: "region", homeRegion: "" }))
      .toMatch(/Set your region/);
  });

  it("proceeds once one is set", () => {
    expect(
      blockedFromSyncing({ locationPrecision: "region", homeRegion: "Utah, US" }),
    ).toBeUndefined();
  });

  it("never blocks where coordinates are recorded", () => {
    // There is always something to fall back on, and blocking a sync over a
    // blank field would be pedantry rather than protection.
    expect(blockedFromSyncing({ locationPrecision: "exact", homeRegion: "" }))
      .toBeUndefined();
    expect(blockedFromSyncing({ locationPrecision: "fuzzed", homeRegion: "" }))
      .toBeUndefined();
  });
});

describe("a sync under each setting", () => {
  let server: FakeFieldServer;
  let repository: MemoryCaptureRepository;
  let precision: LocationPrecision;

  function engine() {
    const media = new MemoryMediaSource();
    media.put("/tmp/a.wav", AUDIO);
    return new SyncEngine({
      repository,
      client: new FieldServerClient("http://server", server, "tok"),
      media,
      rawMedia: media,
      families: new MemoryFamilyRepository(),
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => precision,
    });
  }

  async function record(): Promise<string> {
    const capture: NewCapture = {
      uuid: newClientUuid(randomBytes),
      mediaUuid: newClientUuid(randomBytes),
      recordedAt: "2026-07-27T10:00:00.000Z",
      durationMs: 4000,
      sampleRate: 48_000,
      channels: 1,
      audioPath: "/tmp/a.wav",
      bytes: AUDIO.byteLength,
      latitude: 40.7460,
      longitude: -111.8747,
      region: "Utah, US",
    };
    await repository.add(capture);
    return capture.uuid;
  }

  beforeEach(async () => {
    server = new FakeFieldServer();
    repository = new MemoryCaptureRepository();
    precision = "exact";
    await record();
  });

  it("sends coordinates at exact", async () => {
    await engine().syncAll();
    expect(server.lastCapture?.latitude).toBeCloseTo(40.7460);
  });

  it("sends the snapped point and its radius at fuzzed", async () => {
    precision = "fuzzed";

    await engine().syncAll();

    const snapped = fuzzedCoords(40.7460, -111.8747, 5);
    expect(server.lastCapture?.latitude).toBeCloseTo(snapped.latitude, 10);
    expect(server.lastCapture?.longitude).toBeCloseTo(snapped.longitude, 10);
    // The mark beside the point: without it the corpus holds a fix five miles
    // wide that reads as exact forever.
    expect(server.lastCapture?.coord_fuzz_miles).toBe(5);
  });

  it("sends none at region, and says the region instead", async () => {
    precision = "region";

    await engine().syncAll();

    expect(server.lastCapture?.latitude).toBeUndefined();
    expect(server.lastCapture?.region).toBe("Utah, US");
  });

  it("stops sending them for a capture recorded before the setting changed", async () => {
    // The reason the gate is on the way out rather than at record time: someone
    // who tightens the setting expects the recordings already on the phone to
    // stop carrying coordinates too, not just the next one.
    const uuid = (await repository.list())[0].uuid;
    await engine().syncAll();
    expect(server.lastCapture?.latitude).toBeCloseTo(40.7460);

    precision = "region";
    await repository.update(uuid, { name: "renamed, to make it push again" });
    await engine().syncAll();

    expect(server.lastCaptureEdit?.latitude).toBeUndefined();
    expect(server.lastCaptureEdit?.region).toBe("Utah, US");
  });
});

describe("censoring, which is a separate question from recording", () => {
  it("hides coordinates that were recorded but censored", () => {
    expect(mayShowCoords("exact", true)).toBe(false);
  });

  it("shows them only when censoring is explicitly off", () => {
    expect(mayShowCoords("exact", false)).toBe(true);
  });

  it("masks when nobody has said — settings from before the split", () => {
    // The only safe reading of "no answer" is "do not show them". A phone
    // upgraded mid-session must not publish a street by omission.
    expect(mayShowCoords("exact", undefined)).toBe(false);
  });

  it("region shows nothing whatever censoring says", () => {
    expect(mayShowCoords("region", false)).toBe(false);
    expect(mayShowCoords("region", true)).toBe(false);
  });
});
