import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { describeCoDetection, percent } from "../../../shared/scan";
import {
  deleteScanContribution,
  promoteScanContribution,
  useFleetConfig,
  useScanContributions,
} from "../api/client";
import type { FleetConfig, RecentScan, ScanContribution, ScanHeard } from "../api/types";
import { formatBytes, formatTime } from "../format";
import { colorForCall, labelText } from "../vocab";
import { Pill } from "./detail-atoms";
import { ScanDetail } from "./ScanDetail";

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
            {row.format ? `${row.format.toUpperCase()} · ` : ""}
            {row.duration_sec != null ? `${row.duration_sec.toFixed(0)} s · ` : ""}
            {formatBytes(row.bytes)}
            {row.latitude != null ? " · located" : ""}
          </div>
        </td>
        <td className="muted">{row.requester_ip ?? "—"}</td>
        <td>
          <Heard heard={row.heard} config={config} />
        </td>
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
          <td colSpan={6} className="scan-detail-cell">
            <ScanDetail row={row} config={config} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

/**
 * The scanner's answer in the row itself, so the pile can be read without
 * opening anything: which bird a photo is of, which calls a recording holds.
 */
function Heard({ heard, config }: { heard: ScanHeard | null; config: FleetConfig | undefined }) {
  if (heard === null) return <span className="muted">no result stored</span>;
  if (heard.kind === "photo") {
    if (heard.verdict === "other") {
      return (
        <>
          Not a corvid
          <div className="muted">looks like {heard.instead ?? "something else"}</div>
        </>
      );
    }
    const sure = heard.probability != null ? ` · ${percent(heard.probability)}` : "";
    if (heard.verdict === "no_bird") {
      return (
        <>
          No bird found
          <div className="muted">
            closest {heard.species ?? "—"}
            {sure}
          </div>
        </>
      );
    }
    return (
      <>
        {heard.species ?? "—"}
        <span className="muted">{sure}</span>
        {heard.birds > 1 ? <div className="muted">{heard.birds} birds in the frame</div> : null}
      </>
    );
  }
  if (heard.species.length === 0) return <span className="muted">no corvid</span>;
  return (
    <>
      {heard.species.join(", ")}
      <div className="pills scan-heard">
        {heard.call_types.map(({ call_type, count }) => (
          <Pill key={call_type} color={colorForCall(config, call_type)}>
            {labelText(config, call_type)}
            {count > 1 ? ` × ${count}` : ""}
          </Pill>
        ))}
        {heard.call_types.length === 0 ? <span className="muted">species only</span> : null}
        {heard.candidates ? (
          <span className="muted">
            {heard.candidates} candidate{heard.candidates === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
      {heard.co_detections.length ? (
        <div className="muted">also {heard.co_detections.map(describeCoDetection).join(", ")}</div>
      ) : null}
    </>
  );
}
