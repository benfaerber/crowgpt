import type { LabelingServices } from "../../src/app/LabelingServices";
import type { ContextRecord } from "../../src/domain/context";
import { DEFAULT_SPECIES, type LabelRecord } from "../../src/domain/labels";
import type { CaptureRecord } from "../../src/domain/types";
import type { AnalysisJob, AnalysisResult } from "../../src/net/serverTypes";

import type { Desk, DeskApi, DeskContext, DeskLabel } from "./DeskApi";

/**
 * The labelling desk's services over HTTP, for one kept scan.
 *
 * On the phone these are a local store and a sync queue. Here there is no
 * store to be ahead of the server: every answer is a request, and what the
 * screen reads back is what the server said it now holds. The scan's public
 * id stands in for the capture's uuid throughout.
 */
export class ScanDeskServices implements LabelingServices {
  readonly config;
  readonly settings = { normalizePlayback: false };
  readonly features = { compare: false, sightings: false, markByEar: false };

  private labelRows: LabelRecord[];
  private contextRows: ContextRecord[];
  private record: CaptureRecord;

  constructor(
    private readonly api: DeskApi,
    private readonly desk: Desk,
    /** Told of every refused or failed write, since the screen expects none. */
    private readonly onFailure: (message: string) => void,
  ) {
    this.config = desk.config;
    this.labelRows = desk.labels.map((row) => this.label(row));
    this.contextRows = desk.context.map((row) => this.event(row));
    this.record = {
      uuid: desk.id,
      mediaUuid: desk.id,
      recordedAt: desk.created_at,
      durationMs: Math.round((desk.duration_sec ?? 0) * 1000),
      sampleRate: 48000,
      channels: 1,
      audioPath: new URL(desk.audio_url, window.location.href).toString(),
      bytes: 0,
      silentConfirmedAt: desk.silent_confirmed_at ?? undefined,
      syncState: "synced",
      serverCaptureId: 0,
      uploadedBytes: 0,
      attempts: 0,
    };
  }

  get capture(): CaptureRecord {
    return this.record;
  }

  get decided(): number {
    return this.labelRows.length;
  }

  readonly labels = {
    forCapture: async () => [...this.labelRows],
    byCallType: async () => [] as LabelRecord[],
  };

  readonly context = {
    forCapture: async () => [...this.contextRows],
    forLabel: async (labelUuid: string) => this.contextRows.filter((row) => row.labelUuid === labelUuid),
  };

  readonly sightings = {
    forCapture: async () => [],
    add: () => Promise.reject(new Error("sightings are not kept for a scan")),
    remove: async () => undefined,
  };

  readonly repository = {
    get: async () => this.record,
    update: async (_uuid: string, patch: Partial<CaptureRecord>) => {
      if ("silentConfirmedAt" in patch) {
        const answer = await this.attempt(this.api.setSilent(patch.silentConfirmedAt !== undefined));
        this.record = { ...this.record, silentConfirmedAt: answer.silent_confirmed_at ?? undefined };
      }
      return this.record;
    },
  };

  /** The scan is the analysis: it ran before this page existed. */
  readonly fieldServer = {
    analysis: async (): Promise<AnalysisResult> => ({
      capture_id: 0,
      duration: this.desk.duration_sec ?? undefined,
      waveform: this.desk.waveform,
      calls: this.desk.calls,
    }),
    job: async (id: number): Promise<AnalysisJob> => ({ id, state: "done" }),
    requestAnalysis: async (): Promise<AnalysisJob> => ({ id: 0, state: "done" }),
  };

  readonly normalized = {
    of: () => Promise.reject(new Error("playback is not boosted in a browser")),
  };

  async addLabel(input: {
    uuid: string;
    callType: string;
    startSec: number;
    endSec: number;
    fromDetection?: boolean;
  }): Promise<LabelRecord> {
    const stored = this.label(
      await this.attempt(
        this.api.putLabel(input.uuid, {
          start_sec: input.startSec,
          end_sec: input.endSec,
          call_type: input.callType,
          from_detection: input.fromDetection ?? false,
        }),
      ),
    );
    this.labelRows = [...this.labelRows.filter((row) => row.uuid !== stored.uuid), stored];
    this.record = { ...this.record, silentConfirmedAt: undefined };
    return stored;
  }

  async setLabelCaller(label: LabelRecord, callerRole?: string): Promise<LabelRecord> {
    const stored = this.label(await this.attempt(this.api.setCaller(label.uuid, callerRole)));
    this.labelRows = this.labelRows.map((row) => (row.uuid === stored.uuid ? stored : row));
    return stored;
  }

  async removeLabel(label: LabelRecord): Promise<void> {
    await this.attempt(this.api.deleteLabel(label.uuid));
    this.labelRows = this.labelRows.filter((row) => row.uuid !== label.uuid);
    this.contextRows = this.contextRows.filter((row) => row.labelUuid !== label.uuid);
  }

  async addContext(input: {
    uuid: string;
    labelUuid?: string;
    key: string;
    startSec?: number;
    endSec?: number;
  }): Promise<ContextRecord> {
    const stored = this.event(
      await this.attempt(
        this.api.putContext(input.uuid, {
          key: input.key,
          label_uuid: input.labelUuid,
          start_sec: input.startSec,
          end_sec: input.endSec,
        }),
      ),
    );
    this.contextRows = [...this.contextRows.filter((row) => row.uuid !== stored.uuid), stored];
    return stored;
  }

  async removeContext(event: ContextRecord): Promise<void> {
    await this.attempt(this.api.deleteContext(event.uuid));
    this.contextRows = this.contextRows.filter((row) => row.uuid !== event.uuid);
  }

  private async attempt<T>(request: Promise<T>): Promise<T> {
    try {
      return await request;
    } catch (failure) {
      this.onFailure(failure instanceof Error ? failure.message : String(failure));
      throw failure;
    }
  }

  private label(row: DeskLabel): LabelRecord {
    return {
      uuid: row.client_uuid,
      captureUuid: this.desk.id,
      callType: row.call_type,
      species: DEFAULT_SPECIES,
      startSec: row.start_sec,
      endSec: row.end_sec,
      configVersion: row.config_version ?? undefined,
      fromDetection: row.from_detection === 1,
      callerRole: row.caller_role ?? undefined,
      createdAt: row.created_at,
    };
  }

  private event(row: DeskContext): ContextRecord {
    return {
      uuid: row.client_uuid,
      captureUuid: this.desk.id,
      labelUuid: row.label_uuid ?? undefined,
      key: row.key,
      startSec: row.start_sec ?? undefined,
      endSec: row.end_sec ?? undefined,
      configVersion: row.config_version ?? undefined,
      createdAt: row.created_at,
    };
  }
}
