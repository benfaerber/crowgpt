import { describe, expect, it } from "vitest";

import { FieldServerClient } from "../../src/net/FieldServerClient";
import type { HttpClient, HttpRequest, HttpResponse } from "../../src/net/HttpClient";

/**
 * The phone tells the server which build it is running, on every request.
 *
 * The fleet question this answers: a fix committed and never installed looks
 * exactly like a fix that didn't work. An afternoon went to that once, with the
 * dashboard showing a phone syncing happily for hours and saying nothing about
 * it running last week's bundle.
 */
class RecordingHttp implements HttpClient {
  readonly sent: HttpRequest[] = [];

  async send(request: HttpRequest): Promise<HttpResponse> {
    this.sent.push(request);
    return { status: 200, body: JSON.stringify({ ok: true, config_version: 1 }) };
  }

  async sendBytes(request: HttpRequest): Promise<HttpResponse> {
    this.sent.push(request);
    return { status: 200, body: JSON.stringify({ id: 1, bytes: 1 }) };
  }
}

const BUILD = { version: 121, commit: "512e11e" };

describe("build headers", () => {
  it("reports the build alongside the bearer token", async () => {
    const http = new RecordingHttp();
    await new FieldServerClient("http://server", http, "tok", BUILD).health();

    expect(http.sent[0].headers).toMatchObject({
      Authorization: "Bearer tok",
      "X-App-Version": "121",
      "X-App-Commit": "512e11e",
    });
  });

  it("reports it on uploads too, which are most of what a sync sends", async () => {
    const http = new RecordingHttp();
    const client = new FieldServerClient("http://server", http, "tok", BUILD);

    await client.uploadChunk(7, new Uint8Array([1, 2, 3]), 0, 3);

    expect(http.sent[0].headers?.["X-App-Version"]).toBe("121");
  });

  it("sends nothing when git could not be read", async () => {
    // A build that doesn't know its own version must not claim v0 — the server
    // keeps the last known answer, and a wrong one would overwrite it.
    const http = new RecordingHttp();
    const client = new FieldServerClient("http://server", http, "tok", {
      version: 0,
      commit: "unknown",
    });

    await client.health();

    expect(http.sent[0].headers).not.toHaveProperty("X-App-Version");
  });

  it("still sends the build with no token, so enrollment is attributable", async () => {
    const http = new RecordingHttp();
    await new FieldServerClient("http://server", http, undefined, BUILD).health();

    expect(http.sent[0].headers).not.toHaveProperty("Authorization");
    expect(http.sent[0].headers?.["X-App-Version"]).toBe("121");
  });
});
