/** The widget stays local to the optional demo. Never gate the static page. */
interface Turnstile {
  render(container: HTMLElement, options: Record<string, unknown>): string;
  reset(id: string): void;
  remove(id: string): void;
}

declare global {
  interface Window { turnstile?: Turnstile }
}

async function load(): Promise<Turnstile> {
  if (window.turnstile) return window.turnstile;
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    const timeout = window.setTimeout(() => reject(new Error("verification unavailable")), 12000);
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.onload = () => {
      clearTimeout(timeout);
      if (window.turnstile) resolve(window.turnstile);
      else reject(new Error("verification unavailable"));
    };
    script.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("verification unavailable"));
    };
    document.head.append(script);
  });
}

export class DemoChallenge {
  private widget?: Turnstile;
  private id?: string;

  /** `action` must be the one the route verifies: a token minted for the
   *  generate buttons does not pass for an upload, nor the reverse. */
  constructor(private readonly action = "demo-generate") {}

  async mount(container: HTMLElement, siteKey: string, ready: (token: string) => void,
              unavailable: () => void): Promise<void> {
    this.widget = await load();
    this.id = this.widget.render(container, {
      sitekey: siteKey,
      action: this.action,
      appearance: "interaction-only",
      callback: ready,
      "expired-callback": () => { ready(""); this.reset(); },
      "error-callback": () => { unavailable(); return true; },
      "timeout-callback": unavailable,
      "unsupported-callback": unavailable,
    });
  }

  reset(): void {
    if (this.id !== undefined) this.widget?.reset(this.id);
  }

  remove(): void {
    if (this.id !== undefined) this.widget?.remove(this.id);
    this.id = undefined;
  }
}
