import type { HttpClient, HttpRequest, HttpResponse } from "./HttpClient";

/**
 * React Native implementation, over XMLHttpRequest rather than `fetch`.
 *
 * Expo's WinterCG `fetch` is the global as of SDK 54 and has its own opinions
 * about bodies; RN's XHR is the layer that reliably takes both a JSON string
 * and raw bytes, and it is what the analyzer client already uses.
 */
export class XhrHttpClient implements HttpClient {
  constructor(private readonly timeoutMs = 30_000) {}

  send(request: HttpRequest): Promise<HttpResponse> {
    return this.perform(request, request.body);
  }

  sendBytes(
    request: Omit<HttpRequest, "body"> & { bytes: Uint8Array },
  ): Promise<HttpResponse> {
    // XHR wants an ArrayBuffer, and a Uint8Array is often a window onto a larger
    // one — handing over `.buffer` would send the whole file for every chunk.
    // Copy out exactly this view's range.
    const buffer = new ArrayBuffer(request.bytes.byteLength);
    new Uint8Array(buffer).set(request.bytes);
    return this.perform(request, buffer);
  }

  private perform(
    request: Omit<HttpRequest, "body">,
    body?: string | ArrayBuffer,
  ): Promise<HttpResponse> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(request.method, request.url);
      xhr.timeout = request.timeoutMs ?? this.timeoutMs;
      for (const [key, value] of Object.entries(request.headers ?? {})) {
        xhr.setRequestHeader(key, value);
      }
      xhr.onload = () => resolve({ status: xhr.status, body: xhr.responseText });
      xhr.onerror = () => reject(new Error(`network error: ${request.method} ${request.url}`));
      xhr.ontimeout = () => reject(new Error(`timed out: ${request.method} ${request.url}`));
      xhr.send(body as XMLHttpRequestBodyInit | undefined);
    });
  }
}
