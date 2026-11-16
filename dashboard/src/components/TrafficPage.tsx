import { useState } from "react";

import { useTraffic } from "../api/client";
import type { TrafficDay, TrafficSummary } from "../api/types";
import { formatTime } from "../format";

/**
 * crowgpt.org's visitors, a day at a time.
 *
 * Views and visitors count only browsers that ran the page's JavaScript (the
 * Cloudflare beacon), so scanners faking a browser are not in them. Visitors
 * are distinct IPs within one day; the IPs are not kept, so a range shows
 * visitor-days, not people. Ben's own visits are in every number.
 */

const RANGES = [7, 30, 90, 365] as const;
const STALE_AFTER_MS = 3 * 3600 * 1000;

type Tally = Record<string, number>;

class Range {
  constructor(readonly days: TrafficDay[]) {}

  total(pick: (s: TrafficSummary) => number): number {
    return this.days.reduce((sum, d) => sum + pick(d.summary), 0);
  }

  kind(name: string): number {
    return this.total((s) => s.kinds[name] ?? 0);
  }

  merged(pick: (s: TrafficSummary) => Tally): [string, number][] {
    const out: Tally = {};
    for (const d of this.days) {
      for (const [key, n] of Object.entries(pick(d.summary) ?? {})) out[key] = (out[key] ?? 0) + n;
    }
    return Object.entries(out).sort((a, b) => b[1] - a[1]);
  }
}

/** Every UTC day from `first` to today, with or without a row. */
function calendar(first: string, days: TrafficDay[]): (TrafficDay | { day: string; missing: true })[] {
  const byDay = new Map(days.map((d) => [d.day, d]));
  const out: (TrafficDay | { day: string; missing: true })[] = [];
  const today = new Date().toISOString().slice(0, 10);
  for (let at = new Date(`${first}T00:00:00Z`); ; at.setUTCDate(at.getUTCDate() + 1)) {
    const key = at.toISOString().slice(0, 10);
    out.push(byDay.get(key) ?? { day: key, missing: true });
    if (key >= today) break;
  }
  return out;
}

export function TrafficPage({ signedIn }: { signedIn: boolean }) {
  const [days, setDays] = useState<number>(30);
  const report = useTraffic(signedIn, days);

  if (report.isPending) return <div className="card muted">Loading…</div>;
  if (report.error) return <div className="card note">Could not load traffic — {report.error.message}</div>;

  const data = report.data!;
  const range = new Range(data.days);
  const stale = !data.last_fetched || Date.now() - Date.parse(data.last_fetched) > STALE_AFTER_MS;

  return (
    <>
      <div className="card">
        <div className="traffic-head">
          <h2>crowgpt.org traffic</h2>
          <div className="traffic-ranges" role="group" aria-label="Range">
            {RANGES.map((n) => (
              <button key={n} className={n === days ? "" : "ghost"} onClick={() => setDays(n)}>
                {n === 365 ? "Year" : `${n} days`}
              </button>
            ))}
          </div>
        </div>
        <div className={stale ? "note traffic-warn" : "note"}>
          {data.last_fetched
            ? `Last pulled from Cloudflare ${formatTime(data.last_fetched)}. `
            : "The traffic worker has not written anything yet. "}
          {stale ? "The traffic worker writes hourly, so this is behind: check its log. " : ""}
          UTC days. Your own visits are counted.
        </div>
        <div className="tiles">
          <Tile label="Page views" value={range.total((s) => s.views)} />
          <Tile label="Visitor-days" value={range.total((s) => s.visitors)} />
          <Tile label="AI assistant fetches" value={range.kind("assistant")} />
          <Tile label="Link previews" value={range.kind("preview")} />
          <Tile label="Search crawls" value={range.kind("search")} />
          <Tile label="AI crawls" value={range.kind("ai crawler")} />
          <Tile label="Probes" value={range.kind("probe")} />
        </div>
        <ViewsChart days={calendar(data.first, data.days)} />
      </div>

      <div className="traffic-grid">
        <Ranked title="Visitors by country" note="Distinct IPs per day, summed over the range."
          rows={range.merged((s) => s.countries)} unit="visitor-days" />
        <Ranked title="Pages opened" note="By anything browser-shaped, scanners included; views above count only real browsers."
          rows={range.merged((s) => s.pages)} unit="loads" />
        <Ranked title="AI assistants" note="An assistant fetching a page for a person, by the name it claims."
          rows={range.merged((s) => s.agents.assistant)} unit="fetches" />
        <Ranked title="Link previews" note="Usually a link being shared."
          rows={range.merged((s) => s.agents.preview)} unit="fetches" />
        <Ranked title="Search and AI crawlers"
          rows={[...range.merged((s) => s.agents.search), ...range.merged((s) => s.agents["ai crawler"])]
            .sort((a, b) => b[1] - a[1])} unit="requests" />
        <Ranked title="Probes" note="Requests hunting for secrets or refused, including scanners using AI names."
          rows={range.merged((s) => s.probes)} unit="requests" />
      </div>
    </>
  );
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="tile">
      <div className="n">{value.toLocaleString()}</div>
      <div className="k">{label}</div>
    </div>
  );
}

function ViewsChart({ days }: { days: (TrafficDay | { day: string; missing: true })[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const height = 160;
  const width = 900;
  const slot = width / Math.max(days.length, 1);
  const peak = Math.max(1, ...days.map((d) => ("missing" in d ? 0 : d.summary.views)));
  const scale = (n: number) => (n / peak) * (height - 24);
  const barWidth = Math.max(1, slot - 2);
  const shown = hover === null ? null : days[hover];

  return (
    <div className="traffic-chart">
      <div className="traffic-chart-title">
        Page views per day
        <span className="muted">
          {shown
            ? "missing" in shown
              ? ` · ${shown.day}: not collected`
              : ` · ${shown.day}: ${shown.summary.views} views, ${shown.summary.visitors} visitors${shown.final ? "" : " (so far)"}`
            : ` · peak ${peak}`}
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img"
        aria-label="Page views per day" onMouseLeave={() => setHover(null)}>
        <line x1="0" x2={width} y1={height - 1} y2={height - 1} className="traffic-axis" />
        {days.map((d, i) => {
          const x = i * slot + (slot - barWidth) / 2;
          const views = "missing" in d ? 0 : d.summary.views;
          const h = scale(views);
          return (
            <g key={d.day} onMouseEnter={() => setHover(i)}>
              <rect x={i * slot} y="0" width={slot} height={height} fill="transparent" />
              {"missing" in d ? (
                <rect x={x} y={height - 3} width={barWidth} height="2" className="traffic-missing" />
              ) : (
                <path d={bar(x, height - 1, barWidth, h)}
                  className={`traffic-bar${d.final ? "" : " provisional"}${hover === i ? " hot" : ""}`} />
              )}
            </g>
          );
        })}
      </svg>
      <div className="traffic-axis-labels muted">
        <span>{days[0]?.day}</span>
        <span>{days[days.length - 1]?.day}</span>
      </div>
    </div>
  );
}

/** A bar anchored to the baseline with its data end rounded. */
function bar(x: number, base: number, w: number, h: number): string {
  if (h <= 0) return "";
  const r = Math.min(4, w / 2, h);
  return `M${x},${base} V${base - h + r} Q${x},${base - h} ${x + r},${base - h} H${x + w - r} Q${x + w},${base - h} ${x + w},${base - h + r} V${base} Z`;
}

function Ranked({ title, note, rows, unit }: { title: string; note?: string; rows: [string, number][]; unit: string }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {note ? <div className="note">{note}</div> : null}
      <table className="traffic-table">
        <tbody>
          {rows.length === 0 ? (
            <tr><td className="muted">None in this range.</td></tr>
          ) : rows.slice(0, 12).map(([key, n]) => (
            <tr key={key}>
              <td className="traffic-key" title={key}>{key}</td>
              <td className="num" title={`${n} ${unit}`}>{n.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
