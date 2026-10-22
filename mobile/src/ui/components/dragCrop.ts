export interface CropAnchor {
  /** Handle positions at the moment the finger landed, in seconds. */
  start: number;
  end: number;
  /** Track width in points and the full recording length, also frozen at touch-down. */
  width: number;
  span: number;
}

export interface CropSpan {
  start: number;
  end: number;
}

/** Handles closer than this would upload an empty or useless file. */
export const MIN_CROP_SPAN_SEC = 0.5;

/**
 * Where a trim handle lands for a given drag.
 *
 * `dxPoints` is cumulative from where the finger went down, so it is applied to
 * the **anchor** — the handle's position at touch-down — not to wherever the
 * handle has since moved. Applying it to the live position re-adds the whole
 * delta every frame, which makes the handle shoot off the screen.
 */
export function cropFromDrag(
  anchor: CropAnchor,
  which: "start" | "end",
  dxPoints: number,
  minSpan = MIN_CROP_SPAN_SEC,
): CropSpan {
  if (anchor.width <= 0) return { start: anchor.start, end: anchor.end };
  const deltaSec = (dxPoints / anchor.width) * anchor.span;

  if (which === "start") {
    const start = Math.min(Math.max(0, anchor.start + deltaSec), anchor.end - minSpan);
    return { start, end: anchor.end };
  }
  const end = Math.max(Math.min(anchor.span, anchor.end + deltaSec), anchor.start + minSpan);
  return { start: anchor.start, end };
}
