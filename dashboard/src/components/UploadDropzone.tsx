import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { uploadCapture, type UploadProgress } from "../api/upload";
import { formatBytes } from "../format";

/**
 * Drop test material straight into the corpus.
 *
 * For a clip to watch the analyzer chew on, or a video to check playback —
 * not for field data, which arrives from the phone carrying GPS and a
 * microphone provenance the browser cannot know. Uploads land under the
 * dashboard's own contributor, so test material stays trivially separable from
 * real recordings instead of quietly mixing into them.
 *
 * Goes through the same create/slot/chunk endpoints the phone uses, so this
 * exercises the real ingest path rather than a convenience back door — which
 * also means a bug here is a bug worth knowing about.
 */
export function UploadDropzone() {
  const [over, setOver] = useState(false);
  const [uploads, setUploads] = useState<UploadProgress[]>([]);
  const picker = useRef<HTMLInputElement>(null);
  const queries = useQueryClient();

  const send = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const chosen = [...files];
    setUploads(
      chosen.map((file) => ({
        file: file.name,
        sentBytes: 0,
        totalBytes: file.size,
        stage: "creating" as const,
      })),
    );

    // One at a time. Several large files in parallel over a home connection
    // just makes each of them slower and the progress unreadable.
    for (const file of chosen) {
      await uploadCapture(file, (progress) =>
        setUploads((current) =>
          current.map((entry) => (entry.file === progress.file ? progress : entry)),
        ),
      );
    }
    await queries.invalidateQueries();
  };

  const busy = uploads.some(
    (upload) => upload.stage !== "done" && upload.stage !== "failed",
  );

  return (
    <div className="card">
      <h2>Add test material</h2>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          void send(event.dataTransfer.files);
        }}
        onClick={() => picker.current?.click()}
        style={{
          border: `2px dashed ${over ? "var(--accent)" : "var(--border)"}`,
          background: over ? "var(--panel2)" : "transparent",
          borderRadius: 8,
          padding: "1.5rem",
          textAlign: "center",
          cursor: "pointer",
          color: "var(--muted)",
          fontSize: ".88rem",
        }}
      >
        {busy ? "Uploading…" : "Drop audio or video here, or click to choose"}
        <div style={{ fontSize: ".78rem", marginTop: ".35rem", opacity: 0.8 }}>
          Lands under the dashboard contributor, not your field captures. Video
          is analyzed too — the analyzer reads its audio track.
        </div>
      </div>
      <input
        ref={picker}
        type="file"
        multiple
        accept="audio/*,video/*"
        style={{ display: "none" }}
        onChange={(event) => void send(event.target.files)}
      />

      {uploads.map((upload) => (
        <div key={upload.file} style={{ marginTop: ".6rem", fontSize: ".85rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>{upload.file}</span>
            <span className="muted">
              {upload.stage === "failed"
                ? "failed"
                : upload.stage === "done"
                  ? "done"
                  : `${formatBytes(upload.sentBytes)} / ${formatBytes(upload.totalBytes)}`}
            </span>
          </div>
          <div className="track" style={{ marginTop: ".25rem" }}>
            <div
              className="fill"
              style={{
                width: `${
                  upload.totalBytes === 0
                    ? 0
                    : (upload.sentBytes / upload.totalBytes) * 100
                }%`,
                background:
                  upload.stage === "failed" ? "var(--bad)" : "var(--accent)",
              }}
            />
          </div>
          {upload.error ? <div className="note">{upload.error}</div> : null}
        </div>
      ))}
    </div>
  );
}
