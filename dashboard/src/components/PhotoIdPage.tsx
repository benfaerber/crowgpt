import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import {
  fetchPhotoIdPhotoUrl,
  forgetPhotoIds,
  uploadPhotoForId,
  usePhotoIds,
} from "../api/client";
import type { PhotoIdentification, PhotoIdResult } from "../api/types";

/**
 * A test bench for the photo classifier: drop a photo, see which corvid
 * analyzer/photo thinks it is, where it found the bird, and whether it used
 * the location.
 *
 * The list is the `photo_identifications` table, newest first, so a reload
 * shows the same results. The classifier runs in the photo worker; a photo
 * that stays "waiting" means that worker is not running on this server.
 */

/** How many species to list under the answer. The rest are near zero. */
const SHOWN = 4;

/** A queued photo older than this is waiting on a worker that is not there. */
const WORKER_PATIENCE_MS = 45_000;

function Photo({ item }: { item: PhotoIdentification }) {
  const [url, setUrl] = useState<string>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    let created: string | undefined;
    let gone = false;
    fetchPhotoIdPhotoUrl(item.id)
      .then((u) => {
        created = u;
        if (gone) URL.revokeObjectURL(u);
        else setUrl(u);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    return () => {
      gone = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [item.id]);

  if (error) return <span className="chat-error">could not load the photo — {error}</span>;
  if (!url) return <span className="chat-meta">loading the photo…</span>;
  const result = item.result;
  const box = result?.bird_box;
  return (
    <div className="photo-id-frame">
      <img src={url} alt={item.original_name ?? "uploaded photo"} />
      {result && box ? (
        <div
          className="photo-id-box"
          title="where the classifier found the bird"
          style={{
            left: `${(box.left / result.width) * 100}%`,
            top: `${(box.top / result.height) * 100}%`,
            width: `${((box.right - box.left) / result.width) * 100}%`,
            height: `${((box.bottom - box.top) / result.height) * 100}%`,
          }}
        />
      ) : null}
    </div>
  );
}

function percent(probability: number): string {
  const value = probability * 100;
  return value >= 99.5 ? ">99%" : value < 1 ? "<1%" : `${value.toFixed(0)}%`;
}

function Notes({ item, result }: { item: PhotoIdentification; result: PhotoIdResult }) {
  const located = result.latitude !== null && result.longitude !== null;
  const place = located
    ? `${result.latitude!.toFixed(3)}, ${result.longitude!.toFixed(3)}`
    : undefined;
  const source = item.latitude !== null ? "as entered" : "from the photo's GPS tags";
  return (
    <ul className="photo-id-notes">
      {result.used_location ? (
        <li>Location used: {place} ({source}).</li>
      ) : located ? (
        <li className="warn">
          Location {place} ignored: none of the species it knows is recorded near there.
        </li>
      ) : (
        <li>No location, so judged on the picture alone. Location settles most look-alikes.</li>
      )}
      {result.bird_box ? (
        result.bird_box.birds > 1 ? (
          <li>{result.bird_box.birds} birds found; the largest was judged.</li>
        ) : null
      ) : (
        <li className="warn">No bird found. This answer describes the whole photo.</li>
      )}
    </ul>
  );
}

function Answer({ item }: { item: PhotoIdentification }) {
  if (item.state === "failed") {
    return <span className="chat-error">Could not identify it — {item.error}</span>;
  }
  if (item.state !== "done" || !item.result) {
    const waited = Date.now() - new Date(item.created_at).getTime();
    return (
      <div>
        <span className="chat-typing" aria-label="identifying">
          <span /><span /><span />
        </span>
        <p className="chat-meta">
          {item.state === "running"
            ? "Looking at it. The first photo after a quiet spell takes longer while the models load."
            : waited > WORKER_PATIENCE_MS
              ? "Still waiting. The photo worker does not seem to be running on this server."
              : "Waiting for the photo worker."}
        </p>
      </div>
    );
  }
  const best = item.result.ranking[0];
  return (
    <>
      <h3>{best.common_name}</h3>
      <span className="sci">{best.scientific_name}</span>
      <div className="bars">
        {item.result.ranking.slice(0, SHOWN).map((score) => (
          <div className="bar" key={score.slug}>
            <div className="name">{score.common_name}</div>
            <div className="track">
              <div className="fill" style={{ width: `${score.probability * 100}%` }} />
            </div>
            <div className="v">{percent(score.probability)}</div>
          </div>
        ))}
      </div>
      <Notes item={item} result={item.result} />
    </>
  );
}

export function PhotoIdPage({ signedIn }: { signedIn: boolean }) {
  const feed = usePhotoIds(signedIn);
  const queryClient = useQueryClient();
  const picker = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [sending, setSending] = useState(false);
  const [failure, setFailure] = useState<string>();
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");

  const items = feed.data?.identifications ?? [];
  const halfLocated = Boolean(latitude.trim()) !== Boolean(longitude.trim());

  async function send(files: FileList | null) {
    if (!files || files.length === 0) return;
    setSending(true);
    setFailure(undefined);
    try {
      for (const file of [...files]) {
        await uploadPhotoForId(file, latitude.trim(), longitude.trim());
      }
    } catch (e) {
      setFailure(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
      if (picker.current) picker.current.value = "";
      await queryClient.invalidateQueries({ queryKey: ["photo-ids"] });
    }
  }

  function forget() {
    if (!confirm("Delete every uploaded photo and its result?")) return;
    setFailure(undefined);
    forgetPhotoIds()
      .then(() => queryClient.invalidateQueries({ queryKey: ["photo-ids"] }))
      .catch((e) => setFailure(e instanceof Error ? e.message : String(e)));
  }

  return (
    <div className="card">
      <div className="chat-head">
        <h2>Photo ID</h2>
        <span className="spacer" />
        <button
          className="ghost"
          title="Delete every uploaded photo and its result. Test uploads only — none of these is a capture."
          disabled={items.length === 0}
          onClick={forget}
        >
          Forget
        </button>
      </div>
      <p className="note">
        Upload a photo and the classifier names the corvid in it. It knows nine
        species and always answers with one of them, so a photo of anything
        else still gets a corvid's name. Test uploads; nothing here is, or
        becomes, a capture.
      </p>
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
        {sending ? "Uploading…" : "Drop a photo here, or click to choose"}
        <div style={{ fontSize: ".78rem", marginTop: ".35rem", opacity: 0.8 }}>
          JPEG, PNG or WebP, up to 15 MB.
        </div>
      </div>
      <input
        ref={picker}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/webp"
        style={{ display: "none" }}
        onChange={(event) => void send(event.target.files)}
      />
      <div className="photo-id-coords">
        <span>Where it was taken (optional):</span>
        <input
          type="text"
          inputMode="decimal"
          placeholder="latitude"
          aria-label="latitude"
          value={latitude}
          onChange={(event) => setLatitude(event.target.value)}
        />
        <input
          type="text"
          inputMode="decimal"
          placeholder="longitude"
          aria-label="longitude"
          value={longitude}
          onChange={(event) => setLongitude(event.target.value)}
        />
        <span>
          {halfLocated
            ? "Enter both, or the location is not sent."
            : "Left blank, the photo's own GPS tags are used if it has them."}
        </span>
      </div>
      {failure ? <p className="chat-error">Could not upload — {failure}</p> : null}
      {items.length === 0 && !feed.isPending ? (
        <p className="chat-empty">No photos yet.</p>
      ) : (
        <ul className="photo-id-list">
          {items.map((item) => (
            <li className="photo-id-item" key={item.id}>
              <Photo item={item} />
              <div className="photo-id-answer">
                <Answer item={item} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
