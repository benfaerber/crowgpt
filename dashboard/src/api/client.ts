import { useQuery } from "@tanstack/react-query";

import type {
  CaptureDetail,
  Contributor,
  Device,
  Family,
  FamilyDetail,
  FleetCapture,
  FleetConfig,
  FleetSummary,
  LabelTotal,
} from "./types";
import type { CallContextMatrix, DeviceLog, LogLevel, RelabelRow } from "./types";
import type { Generation, GenerationFeed, ListeningPool, TrainingStatus } from "./types";
import type {
  CorpusPage,
  CorpusRecordingDetail,
  CorpusSummary,
} from "./types";
import type { ServerBuild } from "../buildInfo";

const TOKEN_KEY = "cawtalker_token";
const SECRET_KEY = "cawtalker_operator_secret";

/**
 * The dashboard authenticates with a device bearer token like everything else,
 * but an operator holds the *operator secret* — a different string. The exchange
 * happens server-side at /api/operator/session; pasting one and being told to
 * fetch the other with curl is a trap people actually fell into.
 */
/**
 * localStorage, but it is allowed to be unavailable.
 *
 * EVERY ACCESS HERE USED TO BE BARE, AND FIREFOX MADE THAT FATAL. Reading or
 * writing localStorage THROWS — it does not return null — when the browser has
 * blocked storage for the origin: Enhanced Tracking Protection on strict,
 * "block cookies and site data", or a per-site exception. On Firefox that turned
 * Connect into a button that does nothing: the token exchange succeeded, the
 * write threw, the error escaped into React, and the sign-in never completed
 * with nothing said. The rating pages survived the same setting only because
 * their one call is already wrapped in try/catch.
 *
 * Degrading to in-memory keeps the dashboard usable for the session — you sign
 * in, it works, it forgets when you close the tab — which is a far better answer
 * than a dead button. `storageBlocked()` lets the UI say so.
 */
let memoryStore: Record<string, string> = {};
let blocked = false;

export function storageBlocked(): boolean {
  return blocked;
}

function readKey(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    blocked = true;
    return memoryStore[key] ?? null;
  }
}

function writeKey(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    blocked = true;
  }
  // Mirrored unconditionally: a browser that throws on write may still return
  // a stale value on read, and the two disagreeing is worse than either.
  if (value === null) delete memoryStore[key];
  else memoryStore[key] = value;
}

export function storedToken(): string {
  return readKey(TOKEN_KEY) ?? "";
}

export function storeToken(token: string): void {
  writeKey(TOKEN_KEY, token);
}

export function clearToken(): void {
  writeKey(TOKEN_KEY, null);
  writeKey(SECRET_KEY, null);
}

/**
 * Keep the operator secret in this browser so the dashboard can let itself back
 * in.
 *
 * The session token alone was not enough: anything that invalidates it — a
 * pruned device row, a cleared browser, a fleet rebuilt from scratch — meant
 * finding the secret again, and the dashboard is the thing you open to *find
 * things out*, not a login to fight.
 *
 * The trade is real and worth naming. This is the fleet's master secret, and a
 * script running on this page could read it, where a session token is at least
 * revocable. On a home network with one operator that is a fair swap; before
 * this is ever reachable from outside, turn it off — `rememberSecret(false)`,
 * or just sign out.
 */
export function rememberSecret(secret: string | null): void {
  writeKey(SECRET_KEY, secret);
}

export function hasRememberedSecret(): boolean {
  return (readKey(SECRET_KEY) ?? "") !== "";
}

/**
 * Exchange the remembered secret for a fresh session.
 *
 * Called when a request comes back 401/403 rather than on a timer: the session
 * is usually fine, and the only reliable signal that it is not is the server
 * saying so.
 */
export async function recoverSession(): Promise<boolean> {
  const secret = readKey(SECRET_KEY);
  if (!secret) return false;
  try {
    await signIn(secret, true);
    return true;
  } catch {
    // A secret that no longer works is worse than none — it would retry
    // forever against a fleet whose token has been rotated.
    writeKey(SECRET_KEY, null);
    return false;
  }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** The token is wrong or no longer an operator — sign in again rather than retry. */
  get isAuthFailure(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${storedToken()}` },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await reason(response));
  }
  return (await response.json()) as T;
}

/**
 * Flask serves its 4xx pages as HTML. Dumping that into the UI buries the one
 * useful sentence in markup, so pull the reason out.
 */
export async function reason(response: Response): Promise<string> {
  const body = await response.text();
  if (!body.includes("<")) {
    try {
      const parsed = JSON.parse(body) as { error?: string; message?: string };
      return parsed.error ?? parsed.message ?? body.slice(0, 160);
    } catch {
      return body.slice(0, 160) || `HTTP ${response.status}`;
    }
  }
  const match = /<p>([\s\S]*?)<\/p>/i.exec(body) ?? /<h1>([\s\S]*?)<\/h1>/i.exec(body);
  return match ? match[1].replace(/<[^>]+>/g, "").trim() : `HTTP ${response.status}`;
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${storedToken()}`,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError(response.status, await reason(response));
  return (await response.json()) as T;
}

/**
 * Exchange the operator secret for a dashboard bearer token.
 *
 * Sends any session already held: the server keeps a working one rather than
 * rotating, so signing in here doesn't evict another tab.
 */
export async function signIn(operatorToken: string, remember = true): Promise<void> {
  const held = storedToken();
  const response = await fetch("/api/operator/session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(held ? { Authorization: `Bearer ${held}` } : {}),
    },
    body: JSON.stringify({ operator_token: operatorToken }),
  });
  if (!response.ok) throw new ApiError(response.status, await reason(response));
  const body = (await response.json()) as { device_token: string };
  storeToken(body.device_token);
  if (remember) rememberSecret(operatorToken);
}

/**
 * Everything the dashboard reads, in one place.
 *
 * `enabled` gates on holding a token at all, so signing out doesn't fire a
 * volley of requests that will each fail with 401.
 */
export function useFleet(signedIn: boolean) {
  const summary = useQuery({
    queryKey: ["summary"],
    queryFn: () => request<FleetSummary>("/api/fleet/summary"),
    enabled: signedIn,
  });
  const captures = useQuery({
    queryKey: ["captures"],
    queryFn: () => request<FleetCapture[]>("/api/fleet/captures"),
    enabled: signedIn,
  });
  const contributors = useQuery({
    queryKey: ["contributors"],
    queryFn: () => request<Contributor[]>("/api/fleet/contributors"),
    enabled: signedIn,
  });
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => request<Device[]>("/api/fleet/devices"),
    enabled: signedIn,
  });
  const families = useQuery({
    queryKey: ["families"],
    queryFn: () => request<Family[]>("/api/fleet/families"),
    enabled: signedIn,
  });
  const labels = useQuery({
    queryKey: ["labels"],
    queryFn: () => request<LabelTotal[]>("/api/fleet/labels"),
    enabled: signedIn,
  });

  const semantics = useQuery({
    queryKey: ["semantics"],
    queryFn: () => request<CallContextMatrix>("/api/fleet/semantics"),
    enabled: signedIn,
  });

  return { summary, captures, contributors, devices, families, labels, semantics };
}

/**
 * The phones' own log.
 *
 * Its own hook rather than part of `useFleet`, and refetched on an interval:
 * this is the one panel somebody sits watching while reproducing a bug on a
 * handset, and a stale view of it is worse than none.
 */
export function useFleetLogs({
  level,
  tag,
  search,
  limit = 200,
}: { level?: LogLevel; tag?: string; search?: string; limit?: number } = {}) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (level) query.set("level", level);
  if (tag) query.set("tag", tag);
  if (search) query.set("q", search);
  return useQuery({
    queryKey: ["logs", level, tag, search, limit],
    queryFn: () => request<DeviceLog[]>(`/api/fleet/logs?${query}`),
    refetchInterval: 15_000,
  });
}

export function useFleetLogSummary() {
  return useQuery({
    queryKey: ["logSummary"],
    queryFn: () =>
      request<{ counts: Record<string, number>; tags: string[] }>(
        "/api/fleet/logs/summary",
      ),
    refetchInterval: 15_000,
  });
}

/**
 * What the GPU is doing, if anything.
 *
 * Polled rather than pushed, and polled slowly. A training run writes its state
 * on every eval — a thousand steps, roughly two minutes — so anything faster
 * than that is asking a question whose answer has not changed. It also keeps
 * working when nothing is running, which is most of the time: the endpoint
 * answers `source: "none"` rather than erroring, because "no run" is a normal
 * state and not a failure.
 */
/**
 * The listening pools, for the panel that links out to `/listen/`.
 *
 * Polled on the same 20 s beat as training and for the same reason: the number
 * that moves is a cooldown counting down, and a stale one reads as "still
 * locked" when the dose is actually ready.
 */
export function useListening(signedIn: boolean) {
  return useQuery({
    queryKey: ["listening"],
    queryFn: () => request<ListeningPool[]>("/api/listening/pools"),
    enabled: signedIn,
    refetchInterval: 20_000,
  });
}

export function useTraining(signedIn: boolean) {
  return useQuery({
    queryKey: ["training"],
    queryFn: () => request<TrainingStatus>("/api/training"),
    enabled: signedIn,
    refetchInterval: 20_000,
  });
}

/**
 * Labels worth a second look because the vocabulary changed under them.
 *
 * Its own hook rather than part of `useFleet`: it is a slow-moving answer that
 * only changes when somebody edits the vocabulary, so it does not belong in the
 * volley of requests every refresh fires.
 */
export function useRelabelQueue(signedIn: boolean) {
  return useQuery({
    queryKey: ["relabelQueue"],
    queryFn: () => request<RelabelRow[]>("/api/fleet/relabel-queue?limit=50"),
    enabled: signedIn,
    staleTime: 60_000,
  });
}

export async function clearLogs(): Promise<void> {
  const response = await fetch("/api/fleet/logs", {
    method: "DELETE",
    headers: { Authorization: `Bearer ${storedToken()}` },
  });
  if (!response.ok) throw new ApiError(response.status, await reason(response));
}

/**
 * What the server is running, from the same unauthenticated route the phone
 * polls. Read before sign-in too, so the login screen can say what it is a login
 * to — and so a version is available exactly when someone is diagnosing why
 * their token stopped working.
 */
export function useServerBuild() {
  return useQuery({
    queryKey: ["serverBuild"],
    queryFn: async (): Promise<ServerBuild> => {
      const response = await fetch("/api/health");
      if (!response.ok) throw new ApiError(response.status, await reason(response));
      const health = (await response.json()) as { build?: ServerBuild };
      // A server predating this route reports no build at all, which is itself
      // the answer: it is older than the client asking.
      return health.build ?? {
        version: 0, commit: "unknown", committed_at: null, dirty: false, branch: null,
      };
    },
    staleTime: 60_000,
  });
}

/**
 * The fleet's served vocabulary, including one colour per core call class.
 *
 * Read from the server rather than hardcoded so the dashboard and the phone
 * cannot disagree about what a rattle looks like — and so a label added by a
 * config push gets a colour here without a rebuild. Unauthenticated, like the
 * config route itself, and effectively static.
 */
export function useFleetConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: async (): Promise<FleetConfig> => {
      const response = await fetch("/api/config?locale=en");
      if (!response.ok) throw new ApiError(response.status, await reason(response));
      return (await response.json()) as FleetConfig;
    },
    staleTime: Infinity,
  });
}

export function useCaptureDetail(captureId: number | undefined) {
  return useQuery({
    queryKey: ["capture", captureId],
    queryFn: () => request<CaptureDetail>(`/api/fleet/captures/${captureId}`),
    enabled: captureId !== undefined,
  });
}

export function useFamilyDetail(familyId: number | undefined) {
  return useQuery({
    queryKey: ["family", familyId],
    queryFn: () => request<FamilyDetail>(`/api/fleet/families/${familyId}`),
    enabled: familyId !== undefined,
  });
}

/**
 * Fetch a stored original and hand back a blob URL for `<audio src>`.
 *
 * `<audio>` cannot carry an Authorization header and the route is token-gated,
 * so the bytes have to come through fetch first. Callers must revoke the URL
 * when they are done with it or every capture played leaks its own audio.
 */
export async function fetchMediaUrl(mediaId: number): Promise<string> {
  const response = await fetch(`/api/media/${mediaId}/raw`, {
    headers: { Authorization: `Bearer ${storedToken()}` },
  });
  if (!response.ok) throw new ApiError(response.status, await reason(response));
  return URL.createObjectURL(await response.blob());
}

/**
 * The corpus browser. Polled slowly or not at all — the corpus changes when a
 * crawl or a scan finishes, not by the second, and the summary is the only
 * query worth refreshing on a timer.
 */
export function useCorpusSummary(signedIn: boolean) {
  return useQuery({
    queryKey: ["corpus-summary"],
    queryFn: () => request<CorpusSummary>("/api/corpus/summary"),
    enabled: signedIn,
    refetchInterval: 60_000,
  });
}

export interface CorpusFilters {
  source?: string;
  species?: string;
  withCalls?: boolean;
  q?: string;
  sort?: "caw" | "calls" | "duration" | "recent";
  offset?: number;
}

export function useCorpusRecordings(signedIn: boolean, filters: CorpusFilters) {
  const params = new URLSearchParams();
  if (filters.source) params.set("source", filters.source);
  if (filters.species) params.set("species", filters.species);
  if (filters.withCalls) params.set("with_calls", "1");
  if (filters.q) params.set("q", filters.q);
  params.set("sort", filters.sort ?? "caw");
  params.set("limit", "50");
  params.set("offset", String(filters.offset ?? 0));
  return useQuery({
    queryKey: ["corpus-recordings", params.toString()],
    queryFn: () => request<CorpusPage>(`/api/corpus/recordings?${params}`),
    enabled: signedIn,
    placeholderData: (previous) => previous,
  });
}

export function useCorpusRecording(signedIn: boolean, id: number | undefined) {
  return useQuery({
    queryKey: ["corpus-recording", id],
    queryFn: () => request<CorpusRecordingDetail>(`/api/corpus/recordings/${id}`),
    enabled: signedIn && id !== undefined,
  });
}

/** Same blob-URL dance as fetchMediaUrl, for the same header-less <audio>. */
export async function fetchCorpusAudioUrl(recordingId: number): Promise<string> {
  const response = await fetch(`/api/corpus/recordings/${recordingId}/audio`, {
    headers: { Authorization: `Bearer ${storedToken()}` },
  });
  if (!response.ok) throw new ApiError(response.status, await reason(response));
  return URL.createObjectURL(await response.blob());
}

/**
 * Crow Chat. Polls fast only while something is queued or running — a chat
 * with no pending reply changes when somebody presses a button, not by the
 * second.
 */
export function useGenerations(signedIn: boolean) {
  return useQuery({
    queryKey: ["generations"],
    queryFn: () => request<GenerationFeed>("/api/generations"),
    enabled: signedIn,
    refetchInterval: (query) => {
      const live = query.state.data?.generations.some(
        (g) => g.state === "queued" || g.state === "running",
      );
      return live ? 2_000 : 15_000;
    },
  });
}

export function requestGeneration(
  model: string,
  callType?: string,
): Promise<Generation> {
  return post<Generation>(
    "/api/generations",
    callType ? { model, call_type: callType } : { model },
  );
}

/** Forget the whole conversation — rows and clips both, like clearLogs. */
export async function forgetGenerations(): Promise<void> {
  const response = await fetch("/api/generations", {
    method: "DELETE",
    headers: { Authorization: `Bearer ${storedToken()}` },
  });
  if (!response.ok) throw new ApiError(response.status, await reason(response));
}

/** Same blob-URL dance as fetchMediaUrl, for the same header-less <audio>. */
export async function fetchGenerationAudioUrl(id: number): Promise<string> {
  const response = await fetch(`/api/generations/${id}/audio`, {
    headers: { Authorization: `Bearer ${storedToken()}` },
  });
  if (!response.ok) throw new ApiError(response.status, await reason(response));
  return URL.createObjectURL(await response.blob());
}
