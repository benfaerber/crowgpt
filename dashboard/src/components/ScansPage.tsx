import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  deleteScanContribution,
  fetchScanContributionUrl,
  promoteScanContribution,
  useFleetConfig,
  useScanContribution,
  useScanContributions,
} from "../api/client";
import type { FleetConfig, RecentScan, ScanContribution } from "../api/types";
import { formatBytes, formatTime } from "../format";
import { colorForCall, contextText, labelText } from "../vocab";

/**
 * What strangers scanned on the promo site and let the project keep.
 *
 * None of it is a capture. A row here is an unreviewed file with the
 * scanner's guess and, if its visitor used the labelling desk, their own
 * answers. Promoting one is the operator saying it is worth having: it
 * becomes a capture (provenance "scan", never ★ kept) and the visitor's
 * labels go with it, marked as a visitor's.
 */
export function ScansPage({ signedIn }: { signedIn: boolean }) {
  const pile = useScanContributions(signedIn);
  const config = useFleetConfig();
  const queries = useQueryClient();
  const [open, setOpen] = useState<number | undefined>();
  const [busy, setBusy] = useState<number | null>(null);
  const [note, setNote] = useState<string | undefined>();

  const act = async (row: ScanContribution, action: "promote" | "delete") => {
    if (action === "delete" && !window.confirm("Delete this file and what was said about it?")) {
      return;
    }
    setBusy(row.id);
    setNote(undefined);
    try {
      if (action === "promote") {
        const { capture_id } = await promoteScanContribution(row.id);
        setNote(`Promoted to capture ${capture_id}. It is queued for analysis and is not kept.`);
      } else {
        await deleteScanContribution(row.id);
        if (open === row.id) setOpen(undefined);
      }
      await queries.invalidateQueries({ queryKey: ["scans"] });
    } catch (failure) {
      setNote(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(null);
    }
  };

  const rows = pile.data?.contributions ?? [];
  const unreviewed = rows.filter((row) => row.promoted_capture_id === null).length;

  return (
    <>
    <RecentScans rows={pile.data?.recent ?? []} loading={pile.isPending} />
    <div className="card">
      <h2>Kept scans{unreviewed ? ` · ${unreviewed} unreviewed` : ""}</h2>
      <div className="note">
        Files visitors to the Scan page let the project keep. Not captures, and in no count,
        until promoted. A promoted scan is never ★ kept and its labels are marked as a
        visitor&apos;s.
      </div>
      {note ? <div className="note">{note}</div> : null}
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Kept</th>
              <th>File</th>
              <th>From</th>
              <th>Scanner heard</th>
              <th>Visitor said</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted">
                  {pile.isPending ? "Loading…" : "Nothing has been kept yet."}
                </td>
              </tr>
            ) : null}
            {rows.map((row) => (
              <ScanRow
                key={row.id}
                row={row}
                config={config.data}
                open={open === row.id}
                busy={busy === row.id}
                onToggle={() => setOpen(open === row.id ? undefined : row.id)}
                onAct={(action) => void act(row, action)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
    </>
  );
}

/**
 * Every scan the server still holds a row for, kept or not: the hour in which
 * a flood from one address is visible before its rows are pruned.
 */
function RecentScans({ rows, loading }: { rows: RecentScan[]; loading: boolean }) {
  const perAddress = new Map<string, number>();
  for (const row of rows) {
    if (row.requester_ip) {
      perAddress.set(row.requester_ip, (perAddress.get(row.requester_ip) ?? 0) + 1);
    }
  }
  return (
    <div className="card">
      <h2>Scans in the last hour{rows.length ? ` · ${rows.length}` : ""}</h2>
      <div className="note">
        Everything uploaded to the Scan page, kept or not. A row lasts about an hour; the
        file is gone as soon as it is read unless its visitor let the project keep it.
      </div>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Uploaded</th>
              <th>File</th>
              <th>From</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="muted">
                  {loading ? "Loading…" : "Nobody has scanned anything in the last hour."}
                </td>
              </tr>
            ) : null}
            {rows.map((row, index) => (
              <tr key={`${row.created_at}-${index}`}>
                <td className="muted">{formatTime(row.created_at)}</td>
                <td>{row.kind}</td>
                <td className="muted">
                  {row.requester_ip ?? "—"}
                  {row.requester_ip && perAddress.get(row.requester_ip)! > 1
                    ? ` · ${perAddress.get(row.requester_ip)} from here`
                    : ""}
                </td>
                <td>
                  {row.state}
                  {row.keep ? " · kept" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScanRow({
  row,
  config,
  open,
  busy,
  onToggle,
  onAct,
}: {
  row: ScanContribution;
  config: FleetConfig | undefined;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onAct: (action: "promote" | "delete") => void;
}) {
  const promotable = row.kind !== "photo";
  return (
    <>
      <tr>
        <td className="muted">{formatTime(row.created_at)}</td>
        <td>
          {row.kind}
          <div className="muted">
            {row.duration_sec != null ? `${row.duration_sec.toFixed(0)} s · ` : ""}
            {formatBytes(row.bytes)}
            {row.latitude != null ? " · located" : ""}
          </div>
        </td>
        <td className="muted">{row.requester_ip ?? "—"}</td>
        <td>{row.kind === "photo" ? <span className="muted">a photo</span> : `${row.call_count} call region${row.call_count === 1 ? "" : "s"}`}</td>
        <td>
          {row.silent_confirmed_at ? (
            "no calls in it"
          ) : row.label_count ? (
            <>
              {row.label_count} label{row.label_count === 1 ? "" : "s"}
              {row.context_count ? ` · ${row.context_count} context` : ""}
            </>
          ) : (
            <span className="muted">nothing yet</span>
          )}
          {row.promoted_capture_id !== null ? (
            <div className="muted">capture {row.promoted_capture_id}</div>
          ) : null}
        </td>
        <td>
          <button className="ghost" onClick={onToggle}>
            {open ? "Close" : "Open"}
          </button>{" "}
          {promotable ? (
            <button onClick={() => onAct("promote")} disabled={busy}>
              {row.promoted_capture_id !== null ? "Promote again" : "Promote"}
            </button>
          ) : null}{" "}
          <button className="ghost" onClick={() => onAct("delete")} disabled={busy}>
            Delete
          </button>
        </td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={6}>
            <ScanDetail id={row.id} kind={row.kind} config={config} deskUrl={row.desk_url} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

function ScanDetail({
  id,
  kind,
  config,
  deskUrl,
}: {
  id: number;
  kind: ScanContribution["kind"];
  config: FleetConfig | undefined;
  deskUrl: string | null;
}) {
  const detail = useScanContribution(id);
  const file = useKeptFile(id);

  if (detail.isPending) return <div className="muted">Loading…</div>;
  if (!detail.data) return <div className="muted">Could not load this scan.</div>;
  const { labels, context, calls } = detail.data;

  return (
    <div>
      {file.error ? <div className="note">{file.error}</div> : null}
      {file.url && kind === "photo" ? <img src={file.url} alt="" style={{ maxWidth: 360 }} /> : null}
      {file.url && kind === "audio" ? <audio controls src={file.url} /> : null}
      {file.url && kind === "video" ? <video controls src={file.url} style={{ maxWidth: 480 }} /> : null}

      {kind !== "photo" ? (
        <table>
          <thead>
            <tr>
              <th>Span</th>
              <th>Scanner</th>
              <th>Visitor</th>
              <th>Context</th>
            </tr>
          </thead>
          <tbody>
            {spans(calls, labels).map((span) => (
              <tr key={`${span.start}-${span.end}`}>
                <td className="muted">
                  {span.start.toFixed(1)}–{span.end.toFixed(1)} s
                </td>
                <td style={{ color: colorForCall(config, span.heard) }}>
                  {span.heard ? labelText(config, span.heard) : <span className="muted">—</span>}
                </td>
                <td style={{ color: colorForCall(config, span.label?.call_type) }}>
                  {span.label ? labelText(config, span.label.call_type) : <span className="muted">—</span>}
                  {span.label?.caller_role ? <span className="muted"> · {span.label.caller_role}</span> : null}
                </td>
                <td className="muted">
                  {span.label
                    ? context
                        .filter((event) => event.label_uuid === span.label?.client_uuid)
                        .map((event) => contextText(config, event.key))
                        .join(", ")
                    : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {deskUrl ? (
        <div className="muted">
          The visitor&apos;s labelling link: <a href={deskUrl} style={{ color: "inherit" }}>{deskUrl}</a>
        </div>
      ) : null}
    </div>
  );
}

interface Span {
  start: number;
  end: number;
  heard?: string | null;
  label?: { client_uuid: string; call_type: string; caller_role: string | null };
}

/** Every detection with the label on the same span beside it, then labels on spans of their own. */
function spans(
  calls: { start_sec: number; end_sec: number; call_type?: string | null }[],
  labels: { client_uuid: string; start_sec: number; end_sec: number; call_type: string; caller_role: string | null }[],
): Span[] {
  const same = (a: number, b: number) => Math.abs(a - b) < 0.01;
  const claimed = new Set<string>();
  const out: Span[] = calls.map((call) => {
    const label = labels.find(
      (candidate) =>
        !claimed.has(candidate.client_uuid) &&
        same(candidate.start_sec, call.start_sec) &&
        same(candidate.end_sec, call.end_sec),
    );
    if (label) claimed.add(label.client_uuid);
    return { start: call.start_sec, end: call.end_sec, heard: call.call_type, label };
  });
  for (const label of labels) {
    if (!claimed.has(label.client_uuid)) out.push({ start: label.start_sec, end: label.end_sec, label });
  }
  return out.sort((a, b) => a.start - b.start);
}

/** The kept file as a blob URL, since the route wants a header a media element cannot send. */
function useKeptFile(id: number): { url?: string; error?: string } {
  const [state, setState] = useState<{ url?: string; error?: string }>({});
  useEffect(() => {
    let live = true;
    let made: string | undefined;
    fetchScanContributionUrl(id).then(
      (url) => {
        made = url;
        if (live) setState({ url });
        else URL.revokeObjectURL(url);
      },
      (failure) => live && setState({ error: failure instanceof Error ? failure.message : String(failure) }),
    );
    return () => {
      live = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [id]);
  return state;
}
