/**
 * Who this phone belongs to on the server.
 *
 * A device is a credential, not a person: the same recordist may carry two
 * handsets, and both must reach one corpus. This is what the server said the
 * last time we asked, cached so Settings can answer "whose captures are these?"
 * without a network round-trip — the app is offline-first everywhere else and
 * identity shouldn't be the exception.
 */
export type ContributorRole = "contributor" | "operator" | "admin";

export interface Identity {
  contributorName: string;
  role: ContributorRole;
  /** This handset's row on the server, so it can be renamed. */
  deviceId: number;
  deviceLabel?: string;
  /**
   * The secret that joins another phone to this contributor. Only handed out
   * when this device *created* the contributor; rotate to get a fresh one.
   */
  claimCode?: string;
}

/** A role worth surfacing. Plain contributors don't need to be told they're one. */
export function describeRole(role: ContributorRole): string | undefined {
  if (role === "admin") return "admin";
  if (role === "operator") return "operator";
  return undefined;
}
