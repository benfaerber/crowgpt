import type {
  CorpusNotes,
  CorpusQualityCounts,
  CorpusQualityRow,
  CorpusRecording,
  CorpusTier,
} from "../api/types";

const TIERS: CorpusTier[] = ["high", "mid", "low", "unrated"];

const TIER_TITLES: Record<CorpusTier, string> = {
  high: "top grade (A, ≥4 stars, research grade)",
  mid: "middling grade (B–C, 2.5–4 stars, needs ID)",
  low: "poor grade (D–E, under 2.5 stars, casual)",
  unrated: "the source gave no grade",
};

/** A coverage column: which count it reads, and what it means on hover. */
interface Signal {
  key: keyof CorpusQualityCounts;
  label: string;
  title: string;
}

const SIGNALS: Signal[] = [
  { key: "with_remark", label: "text", title: "the recordist wrote a remark or description" },
  { key: "labelled", label: "call type", title: "the source names the call type (not 'uncertain')" },
  { key: "annotated", label: "timed", title: "a person marked events with timestamps" },
  { key: "background", label: "other spp", title: "other species named as audible — lower is cleaner" },
  { key: "geo", label: "geo", title: "has coordinates" },
  { key: "dated", label: "date", title: "has a recording date" },
  { key: "analyzed", label: "scanned", title: "the detector has been run on it" },
  { key: "with_calls", label: "heard calls", title: "the detector heard at least one confident corvid call" },
];

function percent(part: number, whole: number): number {
  return whole ? Math.round((100 * part) / whole) : 0;
}

function TierBar({ row }: { row: CorpusQualityCounts }) {
  return (
    <div className="quality-tierbar">
      {TIERS.map((tier) => {
        const count = row[`tier_${tier}`];
        if (!count) return null;
        return (
          <span
            key={tier}
            className={`quality-tier-${tier}`}
            style={{ flexGrow: count }}
            title={`${count.toLocaleString()} ${tier} — ${TIER_TITLES[tier]}`}
          />
        );
      })}
    </div>
  );
}

function CoverageCell({ part, whole, title }: { part: number; whole: number; title: string }) {
  const share = percent(part, whole);
  return (
    <td
      className="num quality-cell"
      title={`${part.toLocaleString()} of ${whole.toLocaleString()} — ${title}`}
      style={{ ["--share" as string]: `${share}%` }}
    >
      {part ? `${share}%` : <span className="muted">—</span>}
    </td>
  );
}

/**
 * How well documented each source is: the grade spread and the share of
 * recordings carrying each signal. A row filters the list like the source
 * table above.
 */
export function QualityTable({
  rows,
  totals,
  active,
  onPick,
}: {
  rows: CorpusQualityRow[];
  totals: CorpusQualityCounts | null;
  active?: string;
  onPick: (source: string) => void;
}) {
  if (!rows.length) return null;
  return (
    <>
      <h3 className="quality-heading">Documentation</h3>
      <table className="quality-table">
        <thead>
          <tr>
            <th>source</th>
            <th className="num">recs</th>
            <th className="quality-gradecol" title="grade spread, folded onto one scale">
              grade
            </th>
            {SIGNALS.map((s) => (
              <th key={s.key} className="num" title={s.title}>
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.source}
              className={active === row.source ? "corpus-active" : undefined}
              onClick={() => onPick(row.source)}
            >
              <td>{row.source}</td>
              <td className="num">{row.recordings.toLocaleString()}</td>
              <td>
                <TierBar row={row} />
              </td>
              {SIGNALS.map((s) => (
                <CoverageCell key={s.key} part={row[s.key]} whole={row.recordings} title={s.title} />
              ))}
            </tr>
          ))}
        </tbody>
        {totals ? (
          <tfoot>
            <tr>
              <td>all</td>
              <td className="num">{totals.recordings.toLocaleString()}</td>
              <td>
                <TierBar row={totals} />
              </td>
              {SIGNALS.map((s) => (
                <CoverageCell
                  key={s.key}
                  part={totals[s.key]}
                  whole={totals.recordings}
                  title={s.title}
                />
              ))}
            </tr>
          </tfoot>
        ) : null}
      </table>
      <p className="muted corpus-hint">
        Grade: <span className="quality-key quality-tier-high" /> high{" "}
        <span className="quality-key quality-tier-mid" /> mid{" "}
        <span className="quality-key quality-tier-low" /> low{" "}
        <span className="quality-key quality-tier-unrated" /> unrated. Everything
        here is what the uploader said, not something checked.
      </p>
    </>
  );
}

export function GradeBadge({ grade, tier }: { grade: string | null; tier: CorpusTier }) {
  const shown = grade && grade !== "0.00" ? grade.replace(/\.0+$/, "").replace("_", " ") : "—";
  return (
    <span className={`quality-badge quality-badge-${tier}`} title={TIER_TITLES[tier]}>
      {shown}
    </span>
  );
}

/** The per-row signal chips; absent signals are simply not drawn. */
export function SignalChips({ row }: { row: CorpusRecording }) {
  return (
    <span className="quality-chips">
      {row.remark_chars ? (
        <span className="quality-chip" title={row.remark_preview ?? ""}>
          text {row.remark_chars > 999 ? `${Math.round(row.remark_chars / 1000)}k` : row.remark_chars}
        </span>
      ) : null}
      {row.annotated ? (
        <span className="quality-chip quality-chip-strong" title="timed annotations by a person">
          timed
        </span>
      ) : null}
      {row.background ? (
        <span className="quality-chip quality-chip-warn" title="other species named as audible">
          +spp
        </span>
      ) : null}
      {row.geo ? null : (
        <span className="quality-chip quality-chip-faint" title="no coordinates">
          no geo
        </span>
      )}
    </span>
  );
}

function clock(seconds: number | null): string {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1).padStart(4, "0");
  return m ? `${m}:${s}` : `${s}s`;
}

/** What the source row said about itself, in the opened recording. */
export function SourceNotes({
  notes,
  grade,
  tier,
  callType,
}: {
  notes: CorpusNotes;
  grade: string | null;
  tier: CorpusTier;
  callType: string | null;
}) {
  const flags = Object.entries(notes.flags);
  return (
    <div className="quality-notes">
      <div className="quality-notes-line">
        <GradeBadge grade={grade} tier={tier} />
        {notes.rating_count ? (
          <span className="muted">from {notes.rating_count} ratings</span>
        ) : null}
        {callType ? (
          <span>
            labelled <strong>{callType}</strong>
          </span>
        ) : (
          <span className="muted">no call type given</span>
        )}
        {flags.map(([label, value]) => (
          <span key={label} className="quality-chip quality-chip-faint">
            {label}: {value}
          </span>
        ))}
      </div>

      {notes.remark ? (
        <blockquote className="quality-remark">{notes.remark}</blockquote>
      ) : (
        <p className="muted">The uploader wrote nothing about this one.</p>
      )}

      {notes.background.length ? (
        <p className="quality-background">
          <span className="muted">Also audible, per the uploader:</span>{" "}
          {notes.background.join(", ")}
        </p>
      ) : null}

      {notes.annotations.length ? (
        <table className="corpus-detections quality-annotations">
          <thead>
            <tr>
              <th>human annotation</th>
              <th className="num">from</th>
              <th className="num">to</th>
              <th className="num">labelled s</th>
            </tr>
          </thead>
          <tbody>
            {notes.annotations.slice(0, 40).map((a, index) => (
              <tr key={index}>
                <td>{a.label}</td>
                <td className="num">{clock(a.start_seconds)}</td>
                <td className="num">{clock(a.end_seconds)}</td>
                <td className="num">{a.seconds ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

