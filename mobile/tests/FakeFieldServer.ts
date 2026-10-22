import type { HttpClient, HttpRequest, HttpResponse } from "../src/net/HttpClient";

/**
 * An in-memory stand-in for the field server, implemented at the HTTP seam.
 *
 * Faking here rather than mocking `FieldServerClient` means the tests exercise
 * the real request building — URLs, bearer headers, JSON shapes, and the
 * Content-Range arithmetic that resumable upload depends on. It mirrors the
 * server's actual idempotency semantics: replaying a `client_uuid` returns the
 * existing row, and a media slot reports the byte count it already holds.
 */
export class FakeFieldServer implements HttpClient {
  private captureSeq = 0;
  private mediaSeq = 0;
  private jobSeq = 0;
  private readonly captures = new Map<string, { id: number; client_uuid: string; status: string; family_id: number | null }>();
  private readonly mediaByUuid = new Map<string, number>();
  private readonly media = new Map<number, { id: number; client_uuid: string; bytes: number; upload_state: string }>();
  private dictationSeq = 0;
  private readonly dictationByUuid = new Map<string, number>();
  /** Spoken notes that reached the server, by id. */
  readonly dictations = new Map<number, {
    id: number; client_uuid: string; capture_id: number;
    bytes: number; upload_state: string;
  }>();
  private readonly dictationBytes = new Map<number, Uint8Array>();

  /** Stand in for the transcribe worker having run. */
  transcribe(dictationId: number, text: string): void {
    const row = this.dictations.get(dictationId);
    if (row) (row as { transcript?: string }).transcript = text;
  }

  /** Every client_uuid that was registered as MEDIA — never a spoken note. */
  mediaUuids(): string[] {
    return [...this.mediaByUuid.keys()];
  }
  readonly stored = new Map<number, Uint8Array>();

  /** Every request seen, for asserting that a resume didn't re-send bytes. */
  readonly requests: { method: string; path: string; range?: string }[] = [];

  /** Fail the next N requests with this status (0 = network-level failure). */
  failNext = 0;
  failStatus = 503;
  /** Reply with a Flask-style HTML error page rather than JSON. */
  failHtml = false;
  /** Capture ids this device may not touch, as if minted by another identity. */
  readonly forbidCaptureIds = new Set<number>();

  /** Labels and context events that reached the server, by client uuid. */
  readonly labels = new Map<string, { id: number; capture_id: number; call_type: string }>();
  readonly context = new Map<string, { id: number; label_id?: number; key: string }>();
  /** Out-of-frame sightings — deliberately a different store from context. */
  readonly sightings = new Map<string, { id: number; key: string; offset_sec: number }>();

  async send(request: HttpRequest): Promise<HttpResponse> {
    return this.route(request, request.body);
  }

  async sendBytes(
    request: Omit<HttpRequest, "body"> & { bytes: Uint8Array },
  ): Promise<HttpResponse> {
    return this.route(request, undefined, request.bytes);
  }

  private async route(
    request: Omit<HttpRequest, "body">,
    body?: string,
    bytes?: Uint8Array,
  ): Promise<HttpResponse> {
    const path = request.url.replace(/^https?:\/\/[^/]+/, "");
    this.requests.push({
      method: request.method,
      path,
      range: request.headers?.["Content-Range"],
    });

    if (this.failNext > 0) {
      this.failNext -= 1;
      if (this.failStatus === 0) throw new Error("network error (injected)");
      const body = this.failHtml
        ? "<!doctype html>\n<html lang=en>\n<title>403 Forbidden</title>\n"
          + "<h1>Forbidden</h1>\n<p>not your capture</p>\n"
        : JSON.stringify({ error: "injected" });
      return { status: this.failStatus, body };
    }

    const json = body ? JSON.parse(body) : {};

    if (path === "/api/devices/register") {
      return this.ok({ device_token: "test-token", device: { id: 1 } });
    }

    if (path === "/api/health") return this.ok({ ok: true, config_version: 1 });

    if (path === "/api/families" && request.method === "POST") {
      const uuid = json.client_uuid as string;
      const existing = this.families.get(uuid);
      if (existing) return this.ok(existing);
      const created = { id: this.families.size + 1, name: json.name as string };
      this.families.set(uuid, created);
      return this.ok(created);
    }

    if (path === "/api/captures" && request.method === "POST") {
      const uuid = json.client_uuid as string;
      this.lastCapture = json;
      const existing = this.captures.get(uuid);
      if (existing) return this.ok(existing);
      const created = {
        id: ++this.captureSeq,
        client_uuid: uuid,
        status: "recording",
        family_id: (json.family_id as number | undefined) ?? null,
      };
      this.captures.set(uuid, created);
      return this.ok(created);
    }

    // Edits to a capture the server already holds — tagging a family back at
    // the desk, correcting a note. The create call only ever runs once.
    const capturePatch = path.match(/^\/api\/captures\/(\d+)$/);
    if (capturePatch && request.method === "PATCH") {
      const id = Number(capturePatch[1]);
      this.lastCaptureEdit = json;
      const existing = [...this.captures.values()].find((c) => c.id === id);
      if (!existing) return { status: 404, body: "{}" };
      if (json.family_id !== undefined) existing.family_id = json.family_id as number;
      return this.ok(existing);
    }

    // Idempotent on client_uuid, like the real ones — a replayed sync must not
    // mint a second row for a label that already landed.
    const labelCreate = path.match(/^\/api\/captures\/(\d+)\/labels$/);
    if (labelCreate && request.method === "POST") {
      const uuid = json.client_uuid as string;
      const existing = this.labels.get(uuid);
      if (existing) return this.ok(existing);
      const created = {
        id: this.labels.size + 1,
        capture_id: Number(labelCreate[1]),
        call_type: json.call_type as string,
      };
      this.labels.set(uuid, created);
      return this.ok(created);
    }

    const contextCreate = path.match(/^\/api\/captures\/(\d+)\/context$/);
    if (contextCreate && request.method === "POST") {
      const uuid = json.client_uuid as string;
      const existing = this.context.get(uuid);
      if (existing) return this.ok(existing);
      const created = {
        id: this.context.size + 1,
        // Undefined for a capture-level event on a confirmed-silent recording.
        label_id: json.label_id as number | undefined,
        key: json.key as string,
      };
      this.context.set(uuid, created);
      return this.ok(created);
    }

    const sightingCreate = path.match(/^\/api\/captures\/(\d+)\/sightings$/);
    if (sightingCreate && request.method === "POST") {
      const uuid = json.client_uuid as string;
      const existing = this.sightings.get(uuid);
      if (existing) return this.ok(existing);
      // The server refuses a sighting with no time; the fake must too, or the
      // client could ship one and the tests would never notice.
      if (json.offset_sec === undefined || json.offset_sec === null) {
        return { status: 400, body: JSON.stringify({ error: "offset_sec required" }) };
      }
      const created = {
        id: this.sightings.size + 1,
        key: json.key as string,
        offset_sec: json.offset_sec as number,
      };
      this.sightings.set(uuid, created);
      return this.ok(created);
    }

    const dictationCreate = path.match(/^\/api\/captures\/(\d+)\/dictations$/);
    if (dictationCreate && request.method === "POST") {
      const uuid = json.client_uuid as string;
      const existing = this.dictationByUuid.get(uuid);
      if (existing !== undefined) return this.ok(this.dictations.get(existing));
      const created = {
        id: ++this.dictationSeq, client_uuid: uuid,
        capture_id: Number(dictationCreate[1]),
        bytes: 0, upload_state: "pending",
      };
      this.dictations.set(created.id, created);
      this.dictationByUuid.set(uuid, created.id);
      this.dictationBytes.set(created.id, new Uint8Array(0));
      return this.ok(created);
    }

    const dictationList = path.match(/^\/api\/captures\/(\d+)\/dictations$/);
    if (dictationList && request.method === "GET") {
      const captureId = Number(dictationList[1]);
      return this.ok([...this.dictations.values()]
        .filter((row) => row.capture_id === captureId));
    }

    const dictationUpload = path.match(/^\/api\/dictations\/(\d+)$/);
    if (dictationUpload && request.method === "PUT") {
      const id = Number(dictationUpload[1]);
      const slot = this.dictations.get(id)!;
      const range = request.headers?.["Content-Range"];
      const [span, totalRaw] = range!.split(" ")[1].split("/");
      const start = Number(span.split("-")[0]);
      const total = Number(totalRaw);
      const existing = this.dictationBytes.get(id)!;
      const grown = new Uint8Array(
        Math.max(existing.byteLength, start + bytes!.byteLength));
      grown.set(existing, 0);
      grown.set(bytes!, start);
      this.dictationBytes.set(id, grown);
      slot.bytes = grown.byteLength;
      slot.upload_state = slot.bytes >= total ? "complete" : "partial";
      return this.ok(slot);
    }

    const mediaCreate = path.match(/^\/api\/captures\/(\d+)\/media$/);
    if (mediaCreate && this.forbidCaptureIds.has(Number(mediaCreate[1]))) {
      return {
        status: 403,
        body: "<!doctype html><html><h1>Forbidden</h1><p>not your capture</p></html>",
      };
    }
    if (mediaCreate && request.method === "POST") {
      const uuid = json.client_uuid as string;
      const existingId = this.mediaByUuid.get(uuid);
      if (existingId !== undefined) return this.ok(this.media.get(existingId));
      const created = { id: ++this.mediaSeq, client_uuid: uuid, bytes: 0, upload_state: "pending" };
      this.media.set(created.id, created);
      this.mediaByUuid.set(uuid, created.id);
      this.stored.set(created.id, new Uint8Array(0));
      return this.ok(created);
    }

    const upload = path.match(/^\/api\/media\/(\d+)$/);
    if (upload && request.method === "PUT") {
      const id = Number(upload[1]);
      const slot = this.media.get(id)!;
      // A finished upload is sealed. The real server has already hashed the
      // assembled bytes, so it refuses a later write rather than let one
      // operator quietly overwrite another recordist's field recording.
      if (slot.upload_state === "complete") {
        return {
          status: 400,
          body: JSON.stringify({
            error: "this upload is already complete and cannot be appended to",
          }),
        };
      }
      const range = request.headers?.["Content-Range"];
      const [span, totalRaw] = range!.split(" ")[1].split("/");
      const start = Number(span.split("-")[0]);
      const total = Number(totalRaw);

      const existing = this.stored.get(id)!;
      const grown = new Uint8Array(Math.max(existing.byteLength, start + bytes!.byteLength));
      grown.set(existing, 0);
      grown.set(bytes!, start);
      this.stored.set(id, grown);

      slot.upload_state = grown.byteLength >= total ? "complete" : "partial";
      // The real server compresses the assembled WAV to FLAC and answers with
      // the row afterwards, so the last chunk's reply reports a size well under
      // the total it was given. Modelled here because the client used to take
      // that as its new offset and go round the loop again, writing into a
      // finished file at an offset that meant nothing in it — a bug this fake
      // was too tidy to reproduce.
      //
      // Kept on the row rather than only in this reply: the compressed size is
      // what every later createMedia reports too, which is the second half of
      // the same bug and the half the tidy version hid completely.
      slot.bytes = slot.upload_state === "complete"
        ? Math.floor(grown.byteLength * 0.7)
        : grown.byteLength;
      return this.ok(slot);
    }

    const observe = path.match(/^\/api\/captures\/(\d+)\/observations$/);
    if (observe && request.method === "POST") {
      const uuid = json.client_uuid as string;
      const existing = this.observations.get(uuid);
      if (existing) {
        existing.body = json.body as string; // a replay carries the latest text
        return this.ok(existing);
      }
      const created = { id: this.observations.size + 1, body: json.body as string };
      this.observations.set(uuid, created);
      return this.ok(created);
    }

    const analyze = path.match(/^\/api\/captures\/(\d+)\/analyze$/);
    if (analyze && request.method === "POST") {
      return this.ok({ id: ++this.jobSeq, state: "queued" });
    }

    return { status: 404, body: JSON.stringify({ error: `no route ${path}` }) };
  }

  private ok(payload: unknown): HttpResponse {
    return { status: 200, body: JSON.stringify(payload) };
  }

  uploadPuts(): { range?: string }[] {
    return this.requests.filter((r) => r.method === "PUT");
  }

  /** Families keyed by client_uuid, mirroring the server's idempotency. */
  readonly families = new Map<string, { id: number; name: string }>();

  /** Observations keyed by client_uuid, mirroring the server's idempotency. */
  readonly observations = new Map<string, { id: number; body: string }>();

  /** family_id the first created capture was attached to. */
  captureFamilyId(_path: string): number | null {
    const first = [...this.captures.values()][0];
    return first ? first.family_id : null;
  }

  /**
   * The body of the most recent capture create and capture edit.
   *
   * For asserting what actually left the phone rather than what it meant to
   * send — the only way to test a privacy rule is to look at the wire.
   */
  lastCapture?: Record<string, unknown>;
  lastCaptureEdit?: Record<string, unknown>;

  /** How many distinct captures actually exist server-side. */
  get captureCount(): number {
    return this.captures.size;
  }
}
