import { ApiError, post, reason, storedToken } from "./client";

/**
 * Putting a file into the corpus from the browser — the chunked-upload
 * protocol, kept apart from the endpoint list in client.ts because this is
 * the one thing there with an algorithm in it.
 */

/** How far an in-flight upload has got. */
export interface UploadProgress {
  file: string;
  sentBytes: number;
  totalBytes: number;
  stage: "creating" | "uploading" | "analyzing" | "done" | "failed";
  error?: string;
}

/** 4 MB: small enough that a dropped connection wastes little, large enough
 *  that a 100 MB video is not 800 round trips. */
const CHUNK_BYTES = 4 * 1024 * 1024;

/**
 * An idempotency key for an upload.
 *
 * Not `crypto.randomUUID()`: that is restricted to secure contexts, and the
 * dashboard is served over plain http on a LAN address — so it is simply
 * undefined exactly where this runs. `getRandomValues` has no such restriction.
 */
function clientId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * The file's extension, or nothing if it has none.
 *
 * `name.split(".").pop()` hands back the whole filename when there is no dot in
 * it, so a file called `crows-tuesday` claimed to be in `crows-tuesday` format.
 * The server now refuses that — a format becomes a filename suffix on disk —
 * and the honest answer for a file that does not say is to let the caller's
 * default stand.
 */
function extensionOf(name: string): string | undefined {
  const dot = name.lastIndexOf(".");
  if (dot <= 0 || dot === name.length - 1) return undefined;
  return name.slice(dot + 1).toLowerCase();
}

/**
 * Put a file into the corpus from the browser.
 *
 * For test material — a clip to watch the analyzer chew on, a video to check
 * playback — rather than for field data, which arrives from the phone with GPS
 * and a microphone provenance this path cannot know. Uploads land under the
 * dashboard's own contributor, so they are trivially separable from real
 * recordings rather than quietly mixed in with them.
 *
 * Uses exactly the endpoints the phone uses, chunked the same way, so this
 * exercises the real ingest path instead of a convenience back door.
 */
export async function uploadCapture(
  file: File,
  onProgress: (progress: UploadProgress) => void,
  requestAnalysis = true,
): Promise<void> {
  const video = file.type.startsWith("video/");
  const total = file.size;
  const report = (stage: UploadProgress["stage"], sentBytes: number, error?: string) =>
    onProgress({ file: file.name, sentBytes, totalBytes: total, stage, error });

  try {
    report("creating", 0);
    const clientUuid = clientId();
    const capture = await post<{ id: number }>("/api/captures", {
      client_uuid: clientUuid,
      name: file.name.replace(/\.[^.]+$/, ""),
      recorded_at: new Date(file.lastModified).toISOString(),
      notes: "uploaded from the dashboard",
    });

    const media = await post<{ id: number }>(`/api/captures/${capture.id}/media`, {
      client_uuid: `${clientUuid}-media`,
      kind: video ? "video" : "audio",
      format: extensionOf(file.name) ?? (video ? "mp4" : "wav"),
    });

    report("uploading", 0);
    for (let offset = 0; offset < total; offset += CHUNK_BYTES) {
      const end = Math.min(offset + CHUNK_BYTES, total);
      const response = await fetch(`/api/media/${media.id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${storedToken()}`,
          "Content-Type": "application/octet-stream",
          "Content-Range": `bytes ${offset}-${end - 1}/${total}`,
        },
        body: file.slice(offset, end),
      });
      if (!response.ok) throw new ApiError(response.status, await reason(response));
      report("uploading", end);
    }

    // Video too. The analyzer decodes with ffmpeg, so an mp4's audio track is
    // as readable as a WAV — the "video has no sound" rule is about the phone,
    // which films muted on purpose, not about a clip dropped in from elsewhere.
    if (requestAnalysis) {
      report("analyzing", total);
      await post(`/api/captures/${capture.id}/analyze`, {});
    }
    report("done", total);
  } catch (error) {
    report("failed", 0, error instanceof Error ? error.message : String(error));
  }
}

