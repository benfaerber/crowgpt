/**
 * Client ids for captures and media.
 *
 * These are the idempotency keys the field server dedupes on, so the only hard
 * requirement is that a device never generates the same one twice; 128 bits is
 * far past that.
 *
 * The byte source is injected because there isn't one that works everywhere:
 * Hermes has **no** `crypto` global — reaching for `crypto.getRandomValues`
 * throws "Property 'crypto' doesn't exist" on the phone, at the exact moment a
 * finished recording is being written to the store — while Node has no
 * `expo-crypto`. See `src/platform/random.ts` for the device implementation.
 */
export type RandomBytes = (length: number) => Uint8Array;

export function newClientUuid(randomBytes: RandomBytes): string {
  return Array.from(randomBytes(16), (b) => b.toString(16).padStart(2, "0")).join("");
}
