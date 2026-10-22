import { beforeEach, describe, expect, it } from "vitest";

import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import { FieldServerClient } from "../../src/net/FieldServerClient";
import type { HttpClient, HttpRequest, HttpResponse } from "../../src/net/HttpClient";
import { Restore, type Downloader } from "../../src/sync/Restore";

/**
 * Pulling captures back down.
 *
 * Sync is push-only by design and stays that way; restore is the exception for
 * a phone that has *lost* a capture, where there is no local truth for the
 * server to contradict. Capture 69 survived a reinstall only because it was on
 * the server, and there was no way to get it back — safe and unreachable.
 */
class FakeServer implements HttpClient {
  captures: unknown[] = [];
  media: Record<number, unknown[]> = {};

  async send(request: HttpRequest): Promise<HttpResponse> {
    const path = request.url.replace(/^https?:\/\/[^/]+/, "");
    if (path === "/api/captures") {
      return { status: 200, body: JSON.stringify(this.captures) };
    }
    const m = path.match(/^\/api\/captures\/(\d+)\/media$/);
    if (m) return { status: 200, body: JSON.stringify(this.media[Number(m[1])] ?? []) };
    return { status: 404, body: "{}" };
  }

  async sendBytes(): Promise<HttpResponse> {
    throw new Error("restore never uploads");
  }
}

class FakeDownloader implements Downloader {
  readonly fetched: string[] = [];
  fail = false;

  async download(url: string, _headers: Record<string, string>, filename: string) {
    if (this.fail) throw new Error("network went away");
    this.fetched.push(url);
    return { path: `/data/restored/${filename}`, bytes: 2048 };
  }
}

const capture = (id: number, uuid: string | null, patch = {}) => ({
  id, client_uuid: uuid, status: "analyzed",
  name: `capture ${id}`, keep: 1, recorded_at: "2026-07-26T09:00:00Z",
  duration_sec: 29.5, latitude: 40.76, longitude: -111.87,
  observer_role: "feeding_now", behavior_guess: "teenagers",
  ...patch,
});

const audio = (id: number, uuid: string) => ({
  id, client_uuid: uuid, kind: "audio", format: "wav",
  sample_rate: 48000, channels: 1, bytes: 2048, upload_state: "complete",
});

describe("restore", () => {
  let server: FakeServer;
  let repository: MemoryCaptureRepository;
  let downloader: FakeDownloader;
  let restore: Restore;

  beforeEach(() => {
    server = new FakeServer();
    repository = new MemoryCaptureRepository();
    downloader = new FakeDownloader();
    restore = new Restore(
      repository,
      new FieldServerClient("http://server", server, "tok"),
      downloader,
    );
  });

  it("brings back a capture the phone no longer has", async () => {
    server.captures = [capture(69, "cap-69")];
    server.media = { 69: [audio(1, "med-69")] };

    const outcome = await restore.run();

    expect(outcome.restored).toEqual(["cap-69"]);
    expect((await repository.list())[0].name).toBe("capture 69");
  });

  it("restores the metadata, not just the audio", async () => {
    // The recording is the irreplaceable part, but a capture stripped of what
    // was written about it comes back as an anonymous wav.
    server.captures = [capture(69, "cap-69")];
    server.media = { 69: [audio(1, "med-69")] };

    await restore.run();

    const [row] = await repository.list();
    expect(row.keep).toBe(true);
    expect(row.observerRole).toBe("feeding_now");
    expect(row.behaviorGuess).toBe("teenagers");
    expect(row.latitude).toBe(40.76);
  });

  it("brings back every annotated field, not the handful it started with", async () => {
    // The regression this exists for: ServerCapture is all-optional, so a field
    // left off it drops out of the rebuilt record without a type error. Capture
    // 69 came back as an anonymous wav with its distance, its head count and
    // its region gone, and nothing said it had ever known them.
    server.captures = [capture(69, "cap-69", {
      region: "Utah, US", distance_band: "5_20m",
      adult_count: 3, juvenile_count: 2, unaged_count: 1,
      app_version: 41, app_commit: "af69ec0",
    })];
    server.media = { 69: [audio(1, "med-69")] };

    await restore.run();

    const [row] = await repository.list();
    expect(row.region).toBe("Utah, US");
    expect(row.distanceBand).toBe("5_20m");
    expect(row.adultCount).toBe(3);
    expect(row.juvenileCount).toBe(2);
    expect(row.unagedCount).toBe(1);
    expect(row.appVersion).toBe(41);
    expect(row.appCommit).toBe("af69ec0");
  });

  it("never carries the crop back, because the audio is already cropped", async () => {
    // CroppedWav uploads the selected span as if it were the whole file, so the
    // restored bytes ARE the crop. Applying it again would cut a second bite
    // out of a recording with no original left on this phone to undo against.
    server.captures = [capture(69, "cap-69", {
      crop_start_sec: 4, crop_end_sec: 12, duration_sec: 8,
    })];
    server.media = { 69: [audio(1, "med-69")] };

    await restore.run();

    const [row] = await repository.list();
    expect(row.cropStartSec).toBeUndefined();
    expect(row.cropEndSec).toBeUndefined();
  });

  it("leaves the family unset rather than pointing at a server id", async () => {
    // `family_id` is a server id; a capture references its family by local
    // uuid. Until restore rebuilds families there is nothing honest to map to.
    server.captures = [capture(69, "cap-69", { family_id: 4 })];
    server.media = { 69: [audio(1, "med-69")] };

    await restore.run();

    expect((await repository.list())[0].familyUuid).toBeUndefined();
  });

  it("marks it as already delivered", async () => {
    // Otherwise the phone re-uploads every restored capture, and shows the lot
    // as "Edited" — a restore that immediately looks like a backlog.
    server.captures = [capture(69, "cap-69")];
    server.media = { 69: [audio(1, "med-69")] };

    await restore.run();

    const [row] = await repository.list();
    expect(row.syncState).toBe("synced");
    expect(row.serverCaptureId).toBe(69);
    expect(row.localRevision).toBe(row.syncedRevision);
  });

  it("leaves a capture the phone already has completely alone", async () => {
    // The push-only rule, preserved where it matters: local is the truth, and
    // restore never overwrites it.
    await repository.add({
      uuid: "cap-69", mediaUuid: "m", recordedAt: "2026-07-26T09:00:00Z",
      durationMs: 1000, sampleRate: 48000, channels: 1,
      audioPath: "/local/original.wav", bytes: 100,
      name: "the name I gave it locally",
    });
    server.captures = [capture(69, "cap-69", { name: "server's older name" })];
    server.media = { 69: [audio(1, "med-69")] };

    const outcome = await restore.run();

    expect(outcome.skipped).toBe(1);
    expect(outcome.restored).toEqual([]);
    const [row] = await repository.list();
    expect(row.name).toBe("the name I gave it locally");
    expect(row.audioPath).toBe("/local/original.wav");
    expect(downloader.fetched).toEqual([]);
  });

  it("skips a capture whose audio never finished uploading", async () => {
    server.captures = [capture(70, "cap-70")];
    server.media = { 70: [{ ...audio(2, "med-70"), upload_state: "partial" }] };

    const outcome = await restore.run();

    expect(outcome.unavailable).toBe(1);
    expect(outcome.restored).toEqual([]);
  });

  it("ignores a capture the server minted with no client uuid", async () => {
    // Dashboard uploads. They were never this phone's to lose.
    server.captures = [capture(85, null)];

    expect((await restore.run()).unavailable).toBe(1);
  });

  it("refuses a client_uuid that could escape onto the filesystem", async () => {
    // Restore is the one path where the server hands the phone a value it then
    // writes to disk (`${uuid}.wav`) and keys the local capture on. A hostile or
    // MITM'd server answering with a traversal steers that write at the phone's
    // own database — the source of truth in a push-only design. Nothing is
    // fetched, and the poisoned row never reaches the repository.
    server.captures = [capture(66, "../../SQLite/cawtalker.db")];
    server.media = { 66: [audio(1, "med-66")] };

    const outcome = await restore.run();

    expect(outcome.restored).toEqual([]);
    expect(outcome.failed).toHaveLength(1);
    expect(downloader.fetched).toEqual([]);
    expect(await repository.list()).toEqual([]);
  });

  it("prefers audio over video", async () => {
    server.captures = [capture(69, "cap-69")];
    server.media = {
      69: [
        { ...audio(9, "vid-69"), kind: "video", format: "mp4" },
        audio(1, "med-69"),
      ],
    };

    await restore.run();

    expect(downloader.fetched[0]).toContain("/api/media/1/raw");
  });

  it("keeps going when one capture fails", async () => {
    // The next one may be the recording that mattered.
    server.captures = [capture(69, "cap-69"), capture(70, "cap-70")];
    server.media = { 69: [audio(1, "med-69")], 70: [audio(2, "med-70")] };
    downloader.fail = true;

    const outcome = await restore.run();

    expect(outcome.failed).toHaveLength(2);
    expect(outcome.restored).toEqual([]);
  });

  it("reports progress so a long restore is not a frozen screen", async () => {
    server.captures = [capture(69, "cap-69"), capture(70, "cap-70")];
    server.media = { 69: [audio(1, "med-69")], 70: [audio(2, "med-70")] };
    const seen: string[] = [];

    await restore.run((done, total) => seen.push(`${done}/${total}`));

    expect(seen).toEqual(["1/2", "2/2"]);
  });
});
