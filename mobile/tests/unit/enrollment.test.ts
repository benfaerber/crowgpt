import { describe, expect, it } from "vitest";

import { FieldServerClient } from "../../src/net/FieldServerClient";
import type { HttpClient, HttpRequest, HttpResponse } from "../../src/net/HttpClient";

/** Records what was sent, so the test can assert on the wire format. */
class RecordingHttp implements HttpClient {
  readonly sent: HttpRequest[] = [];

  constructor(private readonly reply: (request: HttpRequest) => unknown) {}

  async send(request: HttpRequest): Promise<HttpResponse> {
    this.sent.push(request);
    return { status: 201, body: JSON.stringify(this.reply(request)) };
  }

  async sendBytes(): Promise<HttpResponse> {
    throw new Error("enrollment never uploads bytes");
  }
}

const REGISTERED = {
  device_token: "tok-1",
  contributor: {
    id: 4,
    public_uuid: "17aa4d7d0cb6eb030d819277ec44f236",
    display_name: "Ben",
    role: "admin",
    status: "active",
  },
  device: { id: 9, label: "Pixel 10", platform: "android", last_seen_at: null, revoked_at: null },
  claim_code: "abc123XYZ",
};

function body(request: HttpRequest): Record<string, unknown> {
  return JSON.parse(String(request.body ?? "{}")) as Record<string, unknown>;
}

describe("enroll", () => {
  it("sends the device label, so the fleet list can name the handset", async () => {
    const http = new RecordingHttp(() => REGISTERED);
    const client = new FieldServerClient("http://server", http);

    await client.enroll({
      enrollToken: "enroll-secret",
      contributorName: "Ben",
      label: "Pixel 10",
    });

    expect(body(http.sent[0]).label).toBe("Pixel 10");
  });

  it("sends a claim code when joining an existing contributor", async () => {
    const http = new RecordingHttp(() => REGISTERED);
    const client = new FieldServerClient("http://server", http);

    await client.enroll({
      enrollToken: "enroll-secret",
      contributorName: "Ben",
      claimCode: "abc123XYZ",
    });

    expect(body(http.sent[0]).claim_code).toBe("abc123XYZ");
  });

  it("omits an empty claim code rather than sending a blank one", async () => {
    // The server treats a present-but-unrecognised code as a 403, so sending ""
    // would turn "start a new account" into a failed enrollment.
    const http = new RecordingHttp(() => REGISTERED);
    const client = new FieldServerClient("http://server", http);

    await client.enroll({ enrollToken: "s", contributorName: "Ben", claimCode: "" });

    expect(body(http.sent[0]).claim_code).toBeUndefined();
  });

  it("returns the identity the server assigned, not what was asked for", async () => {
    // Joining with a claim code means the server's display name wins — the
    // second phone adopts the account it joined rather than renaming it.
    const http = new RecordingHttp(() => REGISTERED);
    const client = new FieldServerClient("http://server", http);

    const { identity } = await client.enroll({
      enrollToken: "s",
      contributorName: "whatever this phone had typed",
      claimCode: "abc123XYZ",
    });

    expect(identity.contributorName).toBe("Ben");
    expect(identity.role).toBe("admin");
    expect(identity.deviceId).toBe(9);
  });

  it("keeps the claim code when the server issues one", async () => {
    const http = new RecordingHttp(() => REGISTERED);
    const client = new FieldServerClient("http://server", http);

    const { identity } = await client.enroll({ enrollToken: "s", contributorName: "Ben" });

    expect(identity.claimCode).toBe("abc123XYZ");
  });

  it("has no claim code when joining, since only the first device is given one", async () => {
    const http = new RecordingHttp(() => ({ ...REGISTERED, claim_code: undefined }));
    const client = new FieldServerClient("http://server", http);

    const { identity } = await client.enroll({
      enrollToken: "s",
      contributorName: "Ben",
      claimCode: "abc123XYZ",
    });

    expect(identity.claimCode).toBeUndefined();
  });

  it("adopts the returned token for subsequent calls", async () => {
    const http = new RecordingHttp(() => REGISTERED);
    const client = new FieldServerClient("http://server", http);

    await client.enroll({ enrollToken: "s", contributorName: "Ben" });

    expect(client.deviceToken).toBe("tok-1");
  });
});
