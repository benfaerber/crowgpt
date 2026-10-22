import type { FleetSummary } from "../api/types";
import { formatBytes } from "../format";

/** Headline numbers. Single values, so tiles rather than charts. */
export function Tiles({ summary }: { summary?: FleetSummary }) {
  if (!summary) return <div className="muted">Loading…</div>;

  const tiles: [string, string | number, boolean?][] = [
    // Real observations first. The plain capture count is dominated by seeded
    // seeded archive clips and repeated test uploads, so it says nothing about
    // crows — this is the number that does.
    ["Real captures", summary.kept_captures],
    ["Captures (incl. test)", summary.captures],
    ["Detected calls", summary.detected_calls],
    ["Human labels", summary.labels],
    ["Observations", summary.observations],
    // The gap that matters: analyzed audio nobody has confirmed yet.
    ["Needs labelling", summary.unlabelled_captures, summary.unlabelled_captures > 0],
    ["Audio stored", formatBytes(summary.media_bytes)],
    ["Contributors", summary.contributors],
    ["Devices", summary.devices],
  ];

  return (
    <div className="tiles">
      {tiles.map(([label, value, attn]) => (
        <div key={label} className={attn ? "tile attn" : "tile"}>
          <div className="n">{value}</div>
          <div className="k">{label}</div>
        </div>
      ))}
    </div>
  );
}
