import { beforeEach, describe, expect, it } from "vitest";

import { log } from "../../src/app/Log";
import { MemoryLogRepository } from "../../src/data/MemoryLogRepository";
import { FieldServerClient } from "../../src/net/FieldServerClient";
import type { HttpClient, HttpRequest, HttpResponse } from "../../src/net/HttpClient";

/**
 * A failed request is the entry a log exists for.
 *
 * The complaint that produced this: "Send logs" was tapped in airplane mode, it
 * failed, and nothing was written down about the failure. Caught at each call
 * site this is forgotten every time — so it is caught once, where the requests
 * are, and both kinds are caught: a status the server refused, and a request
 * that never reached one.
 */
class Stub implements HttpClient {
  constructor(private readonly reply: () => HttpResponse | never) {}
  async send(_request: HttpRequest): Promise<HttpResponse> {
    return this.reply();
  }
  async sendBytes(): Promise<HttpResponse> {
    return this.reply();
  }
}

const store = new MemoryLogRepository();

beforeEach(async () => {
  await store.clear();
});

/**
 * The client logs through the module singleton, which is the same one the
 * global error handler uses — see app/Log.ts for why that exception exists.
 * Attaching a store to it is what makes the entries readable here.
 */
async function entries(run: (client: FieldServerClient) => Promise<unknown>) {
  log.attach(store);
  const client = new FieldServerClient(
    "http://phone.invalid",
    new Stub(() => {
      throw new Error("network error");
    }),
    "token",
  );
  await run(client).catch(() => undefined);
  await log.flush();
  return store.recent();
}

describe("a request that fails", () => {
  it("is written down when the network is not there", async () => {
    const found = await entries((client) => client.health());
    expect(found[0].level).toBe("warn");
    expect(found[0].tag).toBe("net");
    expect(found[0].message).toContain("GET /api/health failed");
  });

  it("is written down for the log push itself", async () => {
    // The one that must not go missing: the push that carries every other
    // entry. Its failure is recorded locally and goes up on the next one that
    // works, which is how an afternoon out of range stays readable.
    const found = await entries((client) =>
      client.pushLogs([
        { clientUuid: "a", at: "1", level: "warn", tag: "t", message: "m" },
      ]),
    );
    expect(found[0].message).toContain("POST /api/logs failed");
  });

  it("still throws, so callers decide what a failure means", async () => {
    const client = new FieldServerClient(
      "http://phone.invalid",
      new Stub(() => {
        throw new Error("network error");
      }),
      "token",
    );
    await expect(client.health()).rejects.toThrow("network error");
  });

  it("records the status when the server refused it", async () => {
    log.attach(store);
    const client = new FieldServerClient(
      "http://phone.invalid",
      new Stub(() => ({ status: 403, body: "not your capture", headers: {} })),
      "token",
    );
    await client.health().catch(() => undefined);
    await log.flush();
    expect((await store.recent())[0].detail).toMatchObject({ status: 403 });
  });
});
