/**
 * Bound a promise that has no bound of its own.
 *
 * Written for the GPS fix, which is the case that proved why it matters:
 * `getCurrentPositionAsync` has no timeout and simply does not resolve indoors
 * or under cover. Stopping a recording awaited it, and the recorder's `busy`
 * guard was held across that await — so the recording stopped, the tone played,
 * the screen said stopped, and then every subsequent press of the earbud button
 * was silently dropped for as long as the app stayed open. Three presses in and
 * the button was dead with nothing on screen to say why.
 *
 * The general lesson, which is why this is a helper rather than one `race`: any
 * await inside a mutual-exclusion guard is a place the guard can be held
 * forever, and third-party promises do not come with that guarantee.
 *
 * Resolves to `fallback` rather than rejecting. A caller that wanted an
 * exception could throw one; the callers here all want "carry on without it".
 */
export function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  fallback: T,
): Promise<T> {
  return new Promise<T>((resolve) => {
    let settled = false;
    const done = (value: T) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => done(fallback), ms);
    // A rejection is a slow promise that failed, and the caller wanted a value
    // either way — the fallback covers both.
    promise.then(done, () => done(fallback));
  });
}
