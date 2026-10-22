/**
 * One screen at a time may claim the back gesture before the route stack.
 *
 * The map's photo overlay lives inside a WebView, invisible to the route
 * stack — without this, back popped the whole map out from under a zoomed
 * photo. A module-level slot rather than nested BackHandler listeners
 * because listener order depends on effect timing (children mount before
 * parents re-register), which made "who answers first" a race.
 */
let interceptor: (() => boolean) | undefined;

export function setBackInterceptor(handle?: () => boolean): void {
  interceptor = handle;
}

/** True if a screen consumed the back press. */
export function runBackInterceptor(): boolean {
  return interceptor?.() === true;
}
