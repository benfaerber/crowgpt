/**
 * Whether a launch opens on the enrollment screen instead of the capture list.
 *
 * Now that the field server is hosted, a fresh install has nothing to talk to
 * until somebody types the enrollment token, and the old default of
 * "dev-enroll" only ever worked against a server on loopback. Asking up front,
 * before the first recording, is what stops the first sync from failing with
 * a 403 nobody understands. Skipping is per launch, not remembered: a phone
 * that has not enrolled is asked again next time, until it has.
 */
export function asksForEnrollment(enrolled: boolean, skippedThisLaunch: boolean): boolean {
  return !enrolled && !skippedThisLaunch;
}

/** What is wrong with the form, or nothing. */
export function enrollmentProblem(token: string): string | undefined {
  if (token.trim().length === 0) {
    return "Enter the enrollment token you were given.";
  }
  return undefined;
}
