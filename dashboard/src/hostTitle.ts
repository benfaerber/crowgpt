/** The browser tab says which server it is showing. The hosted one keeps the
 *  title the page ships with; anything else — loopback, a LAN address — is a
 *  development server, and two identical tabs are how the wrong one gets
 *  edited. */
export class HostTitle {
  static readonly HOSTED = "field.crowgpt.org";

  constructor(private readonly hostname: string) {}

  get isLocal(): boolean {
    return this.hostname !== HostTitle.HOSTED;
  }

  apply(page: Document): void {
    if (this.isLocal) page.title = "CrowGPT (local) - Field Server";
  }
}
