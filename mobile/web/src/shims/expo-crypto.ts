/** expo-crypto's one function the desk uses, from the browser's own source. */
export function getRandomBytes(length: number): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(length));
}
