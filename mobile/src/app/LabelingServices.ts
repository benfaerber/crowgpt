import type { AnalysisCache } from "../data/AnalysisCache";
import type { CaptureRepository } from "../data/CaptureRepository";
import type { ContextRepository } from "../data/ContextRepository";
import type { LabelRepository } from "../data/LabelRepository";
import type { SightingRepository } from "../data/SightingRepository";
import type { FleetConfig } from "../domain/config";
import type { ContextRecord } from "../domain/context";
import type { LabelRecord } from "../domain/labels";
import type { Settings } from "../domain/settings";
import type { FieldServerClient } from "../net/FieldServerClient";
import type { NormalizedWav } from "../playback/NormalizedWav";

/** The parts of the desk that only make sense where their data exists. */
export interface LabelingFeatures {
  /** "Compare with mine": the labeller has past labels of their own to hear. */
  compare: boolean;
  /** The sighting logger under the deck. */
  sightings: boolean;
  /** There is a capture screen where a call can be marked by ear. */
  markByEar: boolean;
}

/**
 * Everything the labelling desk asks of the app, and nothing else.
 *
 * The desk is one screen in two places: on the phone, over the local store
 * and the sync queue, and in a browser, where someone who uploaded a
 * recording to the Scan page labels it over HTTP (mobile/web). `AppServices`
 * satisfies this as it stands; the web build supplies its own. The desk's
 * components take this type so that neither can grow a dependency the other
 * cannot meet without the compiler saying so.
 */
export interface LabelingServices {
  readonly config: FleetConfig;
  readonly settings: Pick<Settings, "normalizePlayback">;
  readonly features: LabelingFeatures;
  readonly labels: Pick<LabelRepository, "forCapture" | "byCallType">;
  readonly context: Pick<ContextRepository, "forLabel" | "forCapture">;
  readonly sightings: Pick<SightingRepository, "forCapture" | "add" | "remove">;
  readonly repository: Pick<CaptureRepository, "get" | "update">;
  readonly fieldServer: Pick<FieldServerClient, "analysis" | "job" | "requestAnalysis">;
  readonly analysisCache?: AnalysisCache;
  readonly normalized: Pick<NormalizedWav, "of">;

  addLabel(input: {
    uuid: string;
    captureUuid: string;
    callType: string;
    startSec: number;
    endSec: number;
    fromDetection?: boolean;
  }): Promise<LabelRecord>;
  setLabelCaller(label: LabelRecord, callerRole?: string): Promise<LabelRecord>;
  removeLabel(label: LabelRecord): Promise<void>;

  addContext(input: {
    uuid: string;
    captureUuid: string;
    labelUuid?: string;
    key: string;
    startSec?: number;
    endSec?: number;
  }): Promise<ContextRecord>;
  removeContext(event: ContextRecord): Promise<void>;
}
