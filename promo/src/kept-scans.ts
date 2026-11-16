import type { SoundResult } from "./scan-timeline";

export interface KeptScan {
  id: string;
  name: string;
  kind: "audio" | "video";
}

interface DeskCall {
  start_sec: number;
  end_sec: number;
  species: string;
  scientific_name: string;
  call_type: string | null;
  confidence: number | null;
  crow_conf: number;
  candidate: number;
}

interface DeskBody {
  duration_sec: number;
  waveform: number[];
  calls: DeskCall[];
  truncated: boolean;
  located: boolean;
  closed: boolean;
  labels: unknown[];
}

export interface Recalled {
  scan: KeptScan;
  result: SoundResult;
  mediaUrl: string;
  labelled: number;
  closed: boolean;
}

/**
 * The recordings this browser let the project keep, so the Scan page can
 * show them again after a reload or a trip to the labelling desk.
 *
 * Only the scan's id, file name and kind stay in the browser. The result and
 * the sound come back from the field server by that id, which is the same
 * link the labelling desk opens, so a recording the project has deleted
 * simply stops appearing.
 */
export class KeptScans {
  private static readonly KEY = "crowgpt.kept-scans";
  private static readonly MOST = 12;

  constructor(private readonly base: string) {}

  remember(scan: KeptScan): void {
    this.write([scan, ...this.read().filter(kept => kept.id !== scan.id)].slice(0, KeptScans.MOST));
  }

  /** Newest first. One the server no longer has is forgotten; one it could
   *  not be asked about is left for the next visit. */
  async recall(): Promise<Recalled[]> {
    const scans = this.read();
    const found = await Promise.all(scans.map(scan => this.fetch(scan)));
    if (found.includes("gone")) this.write(scans.filter((_, index) => found[index] !== "gone"));
    return found.filter((entry): entry is Recalled => typeof entry === "object");
  }

  private async fetch(scan: KeptScan): Promise<Recalled | "gone" | "unknown"> {
    try {
      const path = `${this.base}/api/scan-desk/${encodeURIComponent(scan.id)}`;
      const response = await fetch(path, { headers: { Accept: "application/json" } });
      if (response.status === 404) return "gone";
      if (!response.ok) return "unknown";
      const body = (await response.json()) as DeskBody;
      return {
        scan,
        mediaUrl: `${path}/audio`,
        labelled: body.labels.length,
        closed: body.closed,
        result: {
          duration_sec: body.duration_sec,
          waveform: body.waveform,
          truncated: body.truncated,
          located: body.located,
          calls: body.calls.map(call => ({
            start: call.start_sec,
            end: call.end_sec,
            species: call.species,
            scientific_name: call.scientific_name,
            call_type: call.call_type,
            confidence: call.confidence,
            crow_conf: call.crow_conf,
            candidate: Boolean(call.candidate),
          })),
        },
      };
    } catch {
      return "unknown";
    }
  }

  private read(): KeptScan[] {
    try {
      const stored: unknown = JSON.parse(localStorage.getItem(KeptScans.KEY) ?? "[]");
      if (!Array.isArray(stored)) return [];
      return stored.filter((entry): entry is KeptScan =>
        typeof entry?.id === "string" && typeof entry?.name === "string"
        && (entry?.kind === "audio" || entry?.kind === "video"));
    } catch {
      return [];
    }
  }

  private write(scans: KeptScan[]): void {
    try {
      localStorage.setItem(KeptScans.KEY, JSON.stringify(scans));
    } catch {
      // A browser that stores nothing still scans; it just does not remember.
    }
  }
}
