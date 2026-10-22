import type { SettingsStore } from "../data/SettingsStore";
import type { Identity } from "../domain/identity";
import type { Settings } from "../domain/settings";
import type { FieldServerClient } from "../net/FieldServerClient";

/**
 * Who this phone is, to the fleet: enrollment, renames, the claim code.
 *
 * Owns the cached identity and every write to it, so "what the server said we
 * are" has one home. The client is a function because the app can point at a
 * different server, which rebuilds the client — an identity manager holding
 * the old one would enroll against a machine we no longer talk to.
 */
export class IdentityManager {
  private current?: Identity;

  constructor(
    private readonly deps: {
      client: () => FieldServerClient;
      store?: SettingsStore<Settings>;
    },
    initial?: Identity,
  ) {
    this.current = initial;
  }

  get identity(): Identity | undefined {
    return this.current;
  }

  /**
   * Join the fleet — as a new contributor, or as another device of an existing
   * one when a claim code is set.
   */
  async enroll(request: {
    enrollToken: string;
    contributorName: string;
    label?: string;
    claimCode?: string;
  }): Promise<Identity> {
    const client = this.deps.client();
    const { identity } = await client.enroll(request);
    await this.deps.store?.saveDeviceToken(client.deviceToken);
    return this.setIdentity(identity);
  }

  /** Re-read the identity from the server — device list, role, renames. */
  async refresh(deviceLabelFallback: string): Promise<Identity> {
    const client = this.deps.client();
    const me = await client.me();

    // A device enrolled before names existed has none, and the prefilled
    // default never counts as a "change" so nothing would ever push it. Adopt
    // it once, here, rather than leaving the fleet list showing "—" for a phone
    // whose Settings clearly says otherwise.
    if (!me.device.label && deviceLabelFallback.trim()) {
      try {
        const named = await client.renameDevice(
          me.device.id, deviceLabelFallback.trim(),
        );
        me.device.label = named.label;
      } catch {
        // Not worth failing a refresh over; the next one tries again.
      }
    }

    return this.setIdentity({
      contributorName: me.contributor.display_name,
      role: me.contributor.role,
      deviceId: me.device.id,
      deviceLabel: me.device.label ?? undefined,
      // The server never returns a claim code on read — it is shown once at
      // enrollment and otherwise only by rotating. Keep the one we hold.
      claimCode: this.current?.claimCode,
    });
  }

  /** Push this handset's name, so the fleet list says "Pixel 10" not "—". */
  async renameDevice(label: string): Promise<void> {
    if (!this.current) return;
    const device = await this.deps.client().renameDevice(this.current.deviceId, label);
    await this.setIdentity({ ...this.current, deviceLabel: device.label ?? undefined });
  }

  /** Push the person's name, and adopt whatever spelling the server settled on. */
  async renameContributor(name: string): Promise<void> {
    const contributor = await this.deps.client().renameContributor(name);
    await this.setIdentity({
      ...(this.current ?? { deviceId: 0, role: "contributor" }),
      contributorName: contributor.display_name,
    } as Identity);
  }

  async rotateClaimCode(): Promise<string> {
    const claimCode = await this.deps.client().rotateClaimCode();
    if (this.current) await this.setIdentity({ ...this.current, claimCode });
    return claimCode;
  }

  /**
   * Drop the cached identity — it belonged to the server that issued the
   * device token, so it goes when the app points somewhere else. Returns the
   * persistence promise for the caller's fire-and-forget bookkeeping.
   */
  forget(): Promise<unknown> | undefined {
    this.current = undefined;
    return this.deps.store?.saveIdentity(undefined);
  }

  private async setIdentity(identity: Identity): Promise<Identity> {
    this.current = identity;
    await this.deps.store?.saveIdentity(identity);
    return identity;
  }
}
