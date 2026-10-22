/**
 * The HTTP seam.
 *
 * Kept behind an interface for two reasons: the sync engine can then be tested
 * on a host with no device, and the React Native implementation can use
 * XMLHttpRequest. That last part is not incidental — Expo installs a WinterCG
 * `fetch` (SDK 54+) whose FormData rejects React Native's `{uri}` parts, and
 * XHR is what still streams a file off disk instead of through JS memory.
 */

export interface HttpResponse {
  status: number;
  body: string;
}

export interface HttpRequest {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url: string;
  headers?: Record<string, string>;
  /** JSON-encoded request body, if any. */
  body?: string;
  /**
   * Override the client's default, in milliseconds.
   *
   * For requests whose *failure* is the useful answer. Asking an unreachable
   * server whether it is there should take seconds, not the thirty an upload is
   * rightly given.
   */
  timeoutMs?: number;
}

export interface HttpClient {
  send(request: HttpRequest): Promise<HttpResponse>;
  /** Upload raw bytes. Separated from `send` because the payload is binary, not a string. */
  sendBytes(
    request: Omit<HttpRequest, "body"> & { bytes: Uint8Array },
  ): Promise<HttpResponse>;
}

export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly url: string,
    readonly body: string,
  ) {
    super(`${status} ${HttpError.reason(body) || url}`);
    this.name = "HttpError";
  }

  /**
   * Flask serves its 4xx pages as HTML. Dumping that into the UI fills the
   * screen with markup and buries the one useful sentence, so pull the reason
   * out and leave the rest in `body` for whoever wants it.
   */
  private static reason(body: string): string {
    if (!body.includes("<")) {
      try {
        const parsed = JSON.parse(body) as { error?: string; message?: string };
        return parsed.error ?? parsed.message ?? body.slice(0, 160);
      } catch {
        return body.slice(0, 160);
      }
    }
    const match = /<p>([\s\S]*?)<\/p>/i.exec(body) ?? /<h1>([\s\S]*?)<\/h1>/i.exec(body);
    return match ? match[1].replace(/<[^>]+>/g, "").trim() : "";
  }

  /**
   * Whether retrying the identical request could plausibly succeed. A 4xx means
   * the request itself is wrong and will stay wrong, so a sync should surface it
   * rather than spin on it; anything else is treated as transient.
   */
  get isRetryable(): boolean {
    return this.status === 0 || this.status === 408 || this.status === 429 || this.status >= 500;
  }
}

/**
 * Whether the server is telling us that a *remembered id* is not ours, or no
 * longer exists. Both mean the local record's link to the server is stale —
 * typically because the device re-enrolled and now has a different identity, so
 * rows minted under the old one are genuinely someone else's.
 */
export function isStaleServerLink(error: unknown): boolean {
  return error instanceof HttpError && (error.status === 403 || error.status === 404);
}

export function isRetryable(error: unknown): boolean {
  if (error instanceof HttpError) return error.isRetryable;
  return true; // network-level failures carry no status and are worth another go
}
