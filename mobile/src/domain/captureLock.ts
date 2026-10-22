/**
 * When the screen is locked, and what it takes to unlock it.
 *
 * Pure, because both answers are rules rather than rendering. The threshold in
 * particular is the whole security of the thing — it is the number that decides
 * whether a pocket can end a recording — and it should be checkable without a
 * phone, a leg and a summer.
 */

/**
 * How far across the track a drag has to travel, as a fraction of what is
 * available.
 *
 * High on purpose. A pocket produces taps and short smears; what it does not
 * produce is a sustained one-directional drag across almost the whole width of
 * a phone, held without release to the end. Lowering this to something that
 * feels nicer in the hand is the same as making the lock weaker, and the
 * failure it prevents is silent and unrecoverable.
 */
export const UNLOCK_FRACTION = 0.85;

/**
 * Whether a released drag of `dx` across `travel` pixels should unlock.
 *
 * `travel <= 0` is the un-laid-out track — before `onLayout` has measured it
 * there is no distance to cross, and treating every drag as complete would make
 * the first touch after mounting an unlock.
 */
export function unlockReached(dx: number, travel: number): boolean {
  if (travel <= 0) return false;
  return dx >= travel * UNLOCK_FRACTION;
}

/**
 * Whether the screen should be covered right now.
 *
 * Only ever during a capture. A lock that also covered an idle screen would be
 * protecting nothing — a stray touch that *starts* a recording costs some disk
 * and is undone by deleting it, which is not the loss this exists to prevent.
 *
 * `unlocked` is per-capture and the caller clears it when recording ends, so the
 * next capture arms itself. A lock somebody has to remember to switch on is off
 * at the moment it was needed.
 */
export function screenLocked({
  enabled,
  recording,
  unlocked,
}: {
  enabled: boolean;
  recording: boolean;
  unlocked: boolean;
}): boolean {
  return enabled && recording && !unlocked;
}
