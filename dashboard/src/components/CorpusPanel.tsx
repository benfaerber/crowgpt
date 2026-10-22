import { useEffect, useState } from "react";
import {
  fetchCorpusAudioUrl,
  useCorpusRecording,
  useCorpusRecordings,
  useCorpusSummary,
} from "../api/client";
import type { CorpusFilters } from "../api/client";
import type { CorpusDetection, CorpusRecording } from "../api/types";

function hms(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m${s % 60 ? ` ${s % 60}s` : ""}`;
  return `${(s / 3600).toFixed(1)}h`;
}

function licenceShort(text: string | null): string {
  if (!text) return "—";
  const match = text.match(/licenses\/([a-z-]+)/);
  if (match) return `cc-${match[1]}`;
  if (/zero|publicdomain/i.test(text)) return "cc0";
  return text.length > 24 ? `${text.slice(0, 24)}…` : text;
}

/**
 * One recording opened up: the detections with timestamps, and the audio with
 * click-to-seek. The player fetches lazily — corpus files run to hundreds of
 * MB and a row must not cost a download just by being opened.
 */
function RecordingDetail({ id, signedIn }: { id: number; signedIn: boolean }) {
  const detail = useCorpusRecording(signedIn, id);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    // A new row reuses this component; the old blob must not play on.
    setAudioUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
    setFailure(null);
  }, [id]);
  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    },
    [audioUrl],
  );

  const load = () => {
    setLoading(true);
    fetchCorpusAudioUrl(id)
      .then(setAudioUrl)
      .catch((error) => setFailure(error instanceof Error ? error.message : String(error)))
      .finally(() => setLoading(false));
  };

  const seek = (start: number) => {
    const player = document.getElementById(`corpus-audio-${id}`) as HTMLAudioElement | null;
    if (player) {
      player.currentTime = Math.max(0, start - 1);
      void player.play();
    }
  };

  if (detail.isLoading) return <p className="muted">Reading…</p>;
  const row = detail.data;
  if (!row) return <p className="muted">Could not load this recording.</p>;

  return (
    <div className="corpus-detail">
      <p className="muted corpus-meta">
        {row.recordist ?? "unknown recordist"} · {row.date ?? "no date"} ·{" "}
        {licenceShort(row.license)} · {row.location ?? "no place"}
        {row.page_url ? (
          <>
            {" · "}
            <a href={row.page_url} target="_blank" rel="noreferrer">
              source page
            </a>
          </>
        ) : null}
      </p>

      {row.playable ? (
        audioUrl ? (
          <audio id={`corpus-audio-${id}`} controls src={audioUrl} className="corpus-player" />
        ) : (
          <button className="corpus-load" onClick={load} disabled={loading}>
            {loading
              ? "Fetching audio…"
              : `Load audio (${hms(row.duration_seconds)})`}
          </button>
        )
      ) : (
        <p className="muted">No audio on disk for this row.</p>
      )}
      {failure ? <p className="note">{failure}</p> : null}

      {row.detections.length ? (
        <table className="corpus-detections">
          <thead>
            <tr>
              <th>at</th>
              <th>span</th>
              <th>species</th>
              <th>conf</th>
              <th>call type</th>
            </tr>
          </thead>
          <tbody>
            {row.detections.map((d: CorpusDetection, index) => (
              <tr
                key={index}
                className={d.candidate ? "corpus-candidate" : undefined}
                onClick={() => seek(d.start_seconds)}
                title={audioUrl ? "click to play from here" : "load the audio to seek"}
              >
                <td className="num">{hms(d.start_seconds)}</td>
                <td className="num">{(d.end_seconds - d.start_seconds).toFixed(1)}s</td>
                <td>
                  {d.species}
                  {d.candidate ? <span className="muted"> (candidate)</span> : null}
                </td>
                <td className="num">{d.confidence?.toFixed(2) ?? "—"}</td>
                <td>{d.call_type ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">The detector heard no corvid in this one.</p>
      )}
    </div>
  );
}

/**
 * The corpus, browsable: what was gathered, what the detector heard in it,
 * and the audio itself. Everything here reads the corpus database the
 * collection tooling maintains; detections are model guesses, and candidate
 * rows say so instead of blending in.
 */
export function CorpusPanel({ signedIn }: { signedIn: boolean }) {
  const summary = useCorpusSummary(signedIn);
  const [filters, setFilters] = useState<CorpusFilters>({ withCalls: true, sort: "caw" });
  const [open, setOpen] = useState<number | undefined>();
  const page = useCorpusRecordings(signedIn, filters);

  const change = (next: Partial<CorpusFilters>) =>
    setFilters((current) => ({ ...current, ...next, offset: 0 }));

  if (summary.isLoading) return <p className="muted">Reading…</p>;
  if (!summary.data?.available) {
    return (
      <div className="panel">
        <h2>Corpus</h2>
        <p className="muted">
          No corpus database at <code>{summary.data?.path}</code>. The
          collection tooling writes it; this page only reads.
        </p>
      </div>
    );
  }

  const totals = summary.data.totals;
  const offset = filters.offset ?? 0;
  const total = page.data?.total ?? 0;

  return (
    <>
      <div className="panel">
        <h2>Corpus</h2>
        {totals ? (
          <p className="muted">
            {totals.recordings.toLocaleString()} recordings ·{" "}
            {totals.hours ?? "?"} h catalogued · {totals.analyzed.toLocaleString()} scanned ·{" "}
            {totals.calls.toLocaleString()} confident calls ({totals.caw_hours} h of caw) ·{" "}
            {totals.candidates.toLocaleString()} candidates awaiting an ear
          </p>
        ) : null}
        <div className="corpus-tables">
          <table>
            <thead>
              <tr>
                <th>source</th>
                <th className="num">recs</th>
                <th className="num">hours</th>
                <th className="num">scanned</th>
                <th className="num">calls</th>
                <th className="num">caw h</th>
              </tr>
            </thead>
            <tbody>
              {summary.data.sources.map((s) => (
                <tr
                  key={s.source}
                  className={filters.source === s.source ? "corpus-active" : undefined}
                  onClick={() =>
                    change({ source: filters.source === s.source ? undefined : s.source })
                  }
                >
                  <td>{s.source}</td>
                  <td className="num">{s.recordings.toLocaleString()}</td>
                  <td className="num">{s.hours ?? "?"}</td>
                  <td className="num">{s.analyzed.toLocaleString()}</td>
                  <td className="num">{s.calls.toLocaleString()}</td>
                  <td className="num">{s.caw_hours}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table>
            <thead>
              <tr>
                <th>heard species</th>
                <th className="num">calls</th>
                <th className="num">recs</th>
                <th className="num">caw min</th>
              </tr>
            </thead>
            <tbody>
              {summary.data.species.slice(0, 12).map((s) => (
                <tr
                  key={s.species}
                  className={filters.species === s.species ? "corpus-active" : undefined}
                  onClick={() =>
                    change({ species: filters.species === s.species ? undefined : s.species })
                  }
                >
                  <td>{s.species}</td>
                  <td className="num">{s.calls.toLocaleString()}</td>
                  <td className="num">{s.recordings.toLocaleString()}</td>
                  <td className="num">{s.caw_minutes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted corpus-hint">
          Click a source or species row to filter; counts are the detector's
          confident guesses, not ground truth.
        </p>
      </div>

      <div className="panel">
        <div className="corpus-controls">
          <input
            placeholder="search recordist / species / ref"
            value={filters.q ?? ""}
            onChange={(event) => change({ q: event.target.value || undefined })}
          />
          <label>
            <input
              type="checkbox"
              checked={filters.withCalls ?? false}
              onChange={(event) => change({ withCalls: event.target.checked })}
            />{" "}
            only recordings with calls
          </label>
          <select
            value={filters.sort}
            onChange={(event) =>
              change({ sort: event.target.value as CorpusFilters["sort"] })
            }
          >
            <option value="caw">most caw first</option>
            <option value="calls">most calls first</option>
            <option value="duration">longest first</option>
            <option value="recent">newest first</option>
          </select>
          <span className="muted">
            {total.toLocaleString()} match{filters.source ? ` in ${filters.source}` : ""}
            {filters.species ? ` · ${filters.species}` : ""}
          </span>
        </div>

        <table className="corpus-list">
          <thead>
            <tr>
              <th>ref</th>
              <th>source</th>
              <th>species</th>
              <th>recordist</th>
              <th className="num">length</th>
              <th className="num">calls</th>
              <th className="num">caw</th>
            </tr>
          </thead>
          <tbody>
            {(page.data?.recordings ?? []).map((r: CorpusRecording) => (
              <>
                <tr
                  key={r.id}
                  className={open === r.id ? "corpus-active" : undefined}
                  onClick={() => setOpen(open === r.id ? undefined : r.id)}
                >
                  <td>{r.source_ref}</td>
                  <td>{r.source}</td>
                  <td>{r.species ?? <span className="muted">—</span>}</td>
                  <td>{r.recordist ?? "—"}</td>
                  <td className="num">{hms(r.duration_seconds)}</td>
                  <td className="num">
                    {r.calls}
                    {r.candidates ? (
                      <span className="muted"> +{r.candidates}?</span>
                    ) : null}
                  </td>
                  <td className="num">{hms(r.caw_seconds)}</td>
                </tr>
                {open === r.id ? (
                  <tr key={`${r.id}-detail`} className="corpus-detail-row">
                    <td colSpan={7}>
                      <RecordingDetail id={r.id} signedIn={signedIn} />
                    </td>
                  </tr>
                ) : null}
              </>
            ))}
          </tbody>
        </table>

        <div className="corpus-pager">
          <button
            disabled={offset === 0}
            onClick={() => setFilters({ ...filters, offset: Math.max(0, offset - 50) })}
          >
            ← newer
          </button>
          <span className="muted">
            {offset + 1}–{Math.min(offset + 50, total)} of {total.toLocaleString()}
          </span>
          <button
            disabled={offset + 50 >= total}
            onClick={() => setFilters({ ...filters, offset: offset + 50 })}
          >
            older →
          </button>
        </div>
      </div>
    </>
  );
}
