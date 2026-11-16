import type { FleetConfig } from "../../src/domain/config";
import type { DetectedCall } from "../../src/net/serverTypes";

/** A label as /api/scan-desk stores it. */
export interface DeskLabel {
  client_uuid: string;
  start_sec: number;
  end_sec: number;
  call_type: string;
  caller_role: string | null;
  from_detection: number;
  config_version: number | null;
  created_at: string;
}

export interface DeskContext {
  client_uuid: string;
  label_uuid: string | null;
  key: string;
  start_sec: number | null;
  end_sec: number | null;
  config_version: number | null;
  created_at: string;
}

export interface Desk {
  id: string;
  kind: "audio" | "video";
  created_at: string;
  duration_sec: number | null;
  waveform: number[];
  calls: DetectedCall[];
  truncated: boolean;
  /** Reviewed by the project: the answers are final and nothing can be changed. */
  closed: boolean;
  audio_url: string;
  config: FleetConfig;
  labels: DeskLabel[];
  context: DeskContext[];
  silent_confirmed_at: string | null;
}

export class DeskError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** The labelling routes for one kept scan. The id in the link is the credential. */
export class DeskApi {
  constructor(
    readonly publicId: string,
    private readonly origin = "",
  ) {}

  get base(): string {
    return `${this.origin}/api/scan-desk/${encodeURIComponent(this.publicId)}`;
  }

  load(): Promise<Desk> {
    return this.call<Desk>("GET", "");
  }

  putLabel(uuid: string, body: { start_sec: number; end_sec: number; call_type: string; from_detection: boolean }) {
    return this.call<DeskLabel>("PUT", `/labels/${uuid}`, body);
  }

  setCaller(uuid: string, callerRole: string | undefined) {
    return this.call<DeskLabel>("PATCH", `/labels/${uuid}`, { caller_role: callerRole ?? null });
  }

  deleteLabel(uuid: string) {
    return this.call<void>("DELETE", `/labels/${uuid}`);
  }

  putContext(uuid: string, body: { key: string; label_uuid?: string; start_sec?: number; end_sec?: number }) {
    return this.call<DeskContext>("PUT", `/context/${uuid}`, body);
  }

  deleteContext(uuid: string) {
    return this.call<void>("DELETE", `/context/${uuid}`);
  }

  setSilent(silent: boolean) {
    return this.call<{ silent_confirmed_at: string | null }>("POST", "/silent", { silent });
  }

  private async call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetch(this.base + path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw new DeskError(await DeskApi.reason(response), response.status);
    return (response.status === 204 ? undefined : await response.json()) as T;
  }

  /** Flask answers an abort with an HTML page; the sentence is in its <p>. */
  private static async reason(response: Response): Promise<string> {
    const text = await response.text();
    const sentence = /<p>([^<]+)<\/p>/.exec(text)?.[1];
    return sentence ?? (text.trim().slice(0, 200) || `the server answered ${response.status}`);
  }
}
