import { useState } from "react";

import { useFleetLogs, useFleetLogSummary, clearLogs } from "../api/client";
import type { DeviceLog, LogLevel } from "../api/types";
import { formatTime } from "../format";

const LEVELS: LogLevel[] = ["debug", "info", "warn", "error"];

/**
 * What the phones have been saying about themselves.
 *
 * The app is used outdoors, and `adb logcat` is only true while a cable is
 * attached — it is also wiped by the reinstall that follows every fix, which is
 * how a startup crash on the Pixel 10 was lost twice in one afternoon. So the
 * phone keeps its own log and pushes it with the next sync, and this is where
 * it gets read.
 *
 * Defaults to warnings and above. Everything is here, but the list that opens
 * by default should be the one worth reading — an unfiltered feed of every
 * capture written and every chunk sent trains the eye straight past it.
 */
export function LogsPanel() {
  const [level, setLevel] = useState<LogLevel>("warn");
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const [expanded, setExpanded] = useState<number | undefined>();
  const logs = useFleetLogs({ level, tag: tag || undefined, search: search || undefined });
  const summary = useFleetLogSummary();
  const counts = summary.data?.counts ?? {};

  return (
    <div className="card">
      <h2>
        App log
        {counts.error ? <span className="pill s-queued"> {counts.error} errors</span> : null}
      </h2>

      <div className="logControls">
        {LEVELS.map((option) => (
          <button
            key={option}
            className={option === level ? undefined : "ghost"}
            onClick={() => setLevel(option)}
            title={`${option} and above`}
          >
            {option}
            {counts[option] ? ` (${counts[option]})` : ""}
          </button>
        ))}
        <select value={tag} onChange={(event) => setTag(event.target.value)}>
          <option value="">every subsystem</option>
          {(summary.data?.tags ?? []).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <input
          placeholder="search messages"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="spacer" />
        <button
          className="ghost"
          title="Throw them away. The useful move after a fix is to wipe and watch."
          onClick={() => {
            if (confirm("Delete every stored log line?")) {
              void clearLogs().then(() => {
                void logs.refetch();
                void summary.refetch();
              });
            }
          }}
        >
          Clear
        </button>
      </div>

      {logs.isPending ? (
        <div className="muted">Loading…</div>
      ) : (logs.data ?? []).length === 0 ? (
        <div className="muted">
          Nothing at this level. Phones push their log on sync — a phone that has
          not synced since the app was updated has not sent one yet.
        </div>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Level</th>
                <th>Where</th>
                <th>Device</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {(logs.data ?? []).map((entry) => (
                <LogRow
                  key={entry.id}
                  entry={entry}
                  open={expanded === entry.id}
                  onToggle={() =>
                    setExpanded((current) => (current === entry.id ? undefined : entry.id))
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function LogRow({
  entry,
  open,
  onToggle,
}: {
  entry: DeviceLog;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: entry.detail ? "pointer" : undefined }}>
        {/* The phone's clock, not ours. A handset that was offline for a week
            pushes week-old lines, and when it happened is the question. */}
        <td className="muted" title={`received ${formatTime(entry.received_at)}`}>
          {formatTime(entry.at)}
        </td>
        <td>
          <span className={`pill lvl-${entry.level}`}>{entry.level}</span>
        </td>
        <td className="muted">{entry.tag}</td>
        <td className="muted" title={entry.app_commit ?? undefined}>
          {entry.device_label ?? `#${entry.device_id}`}
          {entry.app_version ? ` · v${entry.app_version}` : ""}
        </td>
        <td>{entry.message}</td>
      </tr>
      {open && entry.detail ? (
        <tr>
          <td colSpan={5}>
            <pre className="logDetail">{pretty(entry.detail)}</pre>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function pretty(detail: string): string {
  try {
    return JSON.stringify(JSON.parse(detail), null, 2);
  } catch {
    return detail;
  }
}
