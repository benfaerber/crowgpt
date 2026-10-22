import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import type { FleetCapture } from "../api/types";
import { describePlaceForOperator, formatBytes, formatDuration, formatTime } from "../format";
import { SnrGauge } from "./SnrGauge";
import { StatusPill } from "./StatusPill";

const column = createColumnHelper<FleetCapture>();

export function CapturesTable({
  captures,
  loading,
  selectedId,
  onSelect,
  renderExpanded,
}: {
  captures: FleetCapture[];
  loading: boolean;
  selectedId?: number;
  onSelect: (id: number) => void;
  /**
   * Drawn in a full-width row directly beneath the selected one.
   *
   * The detail used to be a card after the whole table, which meant clicking
   * row three and then scrolling past ninety more to read the answer. Beneath
   * the row is where the eye already is.
   */
  renderExpanded?: (capture: FleetCapture) => React.ReactNode;
}) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "when", desc: true }]);
  const [filter, setFilter] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  // How wide the expanded detail may be. It has to be the *visible* width of the
  // horizontal scroller: a percentage inside a table cell resolves against the
  // table, and the table is the thing that is too wide, so the waveform came out
  // the full scroll width and spilled past the card. CSS cannot see this number.
  const [viewport, setViewport] = useState<number>();

  useEffect(() => {
    const box = scroller.current;
    if (!box) return;
    const measure = () => setViewport(box.clientWidth);
    measure();
    // Window resizes, the sidebar-less narrow case, and the detail itself
    // opening and changing the scrollbar — all of them move this.
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  const columns = useMemo(
    () => [
      // Every numeric column states its comparator. TanStack's "auto" picks one
      // by sampling the first row, and these are nullable — a null in that row
      // makes it choose the string comparator, which sorts 10 before 9. The
      // accessors coerce to a number for the same reason: the cell already
      // renders null as 0, and sort order has to match what is on screen.
      column.accessor("id", {
        header: "ID",
        sortingFn: "basic",
        cell: (cell) => <span className="muted">#{cell.getValue()}</span>,
      }),
      // A capture is named by its recordist or, failing that, by its clock.
      // Sorting has to follow what is on screen, so the accessor returns the
      // same string the cell renders.
      column.accessor((row) => row.name ?? formatTime(row.recorded_at ?? row.created_at), {
        id: "capture",
        header: "Capture",
        cell: (cell) =>
          cell.row.original.name ? (
            cell.getValue()
          ) : (
            <span className="muted">{cell.getValue()}</span>
          ),
      }),
      // What the recordist was to these birds. Blank for the great majority —
      // it only started being recorded recently — so it stays a narrow column
      // rather than a prominent one.
      column.accessor((row) => row.observer_role ?? "", {
        id: "observer",
        header: "Known as",
        cell: (cell) =>
          cell.getValue() ? (
            <span>{String(cell.getValue()).replace(/_/g, " ")}</span>
          ) : (
            <span className="muted">—</span>
          ),
      }),
      column.accessor((row) => (row.keep ? "real" : "test"), {
        id: "kind",
        header: "Favorite",
        cell: (cell) =>
          cell.getValue() === "real" ? (
            <span title="marked a real observation">★</span>
          ) : (
            <span className="muted" title="seeded or test material">·</span>
          ),
      }),
      column.accessor("contributor_name", {
        header: "Contributor",
        cell: (cell) => cell.getValue() ?? "—",
      }),
      column.accessor("status", {
        header: "Status",
        cell: (cell) => <StatusPill status={cell.getValue()} />,
      }),
      column.accessor((row) => row.recorded_at ?? row.created_at, {
        id: "when",
        header: "Recorded",
        cell: (cell) => <span className="muted">{formatTime(cell.getValue())}</span>,
      }),
      column.accessor((row) => row.duration_sec ?? 0, {
        id: "duration_sec",
        header: "Dur",
        sortingFn: "basic",
        meta: { numeric: true },
        // The server speaks seconds, the formatter milliseconds.
        cell: (cell) => formatDuration((cell.getValue() || 0) * 1000 || null),
      }),
      // Unmeasured is null, and null is not 0 dB — a real measurement. The
      // sentinel keeps the unmeasured together at the quiet end of a sort
      // while the cell says nothing rather than something.
      column.accessor((row) => row.band_snr_db ?? -1000, {
        id: "band_snr_db",
        header: "SNR",
        sortingFn: "basic",
        meta: { numeric: true },
        cell: (cell) => {
          const row = cell.row.original;
          if (row.quality_measured_at == null) return <span className="muted">—</span>;
          return (
            <span style={{ whiteSpace: "nowrap" }}>
              <SnrGauge db={row.band_snr_db} />
              {row.band_snr_db != null ? ` ${row.band_snr_db.toFixed(1)}` : ""}
            </span>
          );
        },
      }),
      column.accessor((row) => row.call_count ?? 0, {
        id: "call_count",
        header: "Calls",
        sortingFn: "basic",
        meta: { numeric: true },
        cell: (cell) => cell.getValue(),
      }),
      column.accessor((row) => row.label_count ?? 0, {
        id: "label_count",
        header: "Labels",
        sortingFn: "basic",
        meta: { numeric: true },
        cell: (cell) => cell.getValue(),
      }),
      column.accessor((row) => row.observation_count ?? 0, {
        id: "observation_count",
        header: "Notes",
        sortingFn: "basic",
        meta: { numeric: true },
        cell: (cell) => cell.getValue(),
      }),
      column.accessor((row) => row.media_bytes ?? 0, {
        id: "media_bytes",
        header: "Size",
        sortingFn: "basic",
        meta: { numeric: true },
        cell: (cell) => formatBytes(cell.getValue()),
      }),
      column.accessor(
        // Through the shared helper, which knows both the contributor's choice
        // and whether this browser is in presentation mode.
        (row) => row.location_name ?? describePlaceForOperator(row),
        {
          id: "where",
          header: "Location",
          cell: (cell) => <span className="muted">{cell.getValue()}</span>,
        },
      ),
    ],
    [],
  );

  const table = useReactTable({
    data: captures,
    columns,
    state: { sorting, globalFilter: filter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (loading) return <div className="muted">Loading…</div>;
  if (captures.length === 0) return <div className="note">No captures yet.</div>;

  return (
    <>
      <input
        type="text"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        placeholder="Filter by name, contributor, place…"
        style={{ marginBottom: ".75rem", width: "min(24rem, 100%)" }}
      />
      <div className="scroll" ref={scroller}>
        <table>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const numeric = (header.column.columnDef.meta as { numeric?: boolean })
                    ?.numeric;
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      className={numeric ? "num" : undefined}
                      onClick={header.column.getToggleSortingHandler()}
                      style={{ cursor: "pointer", userSelect: "none" }}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {sorted === "asc" ? " ▲" : sorted === "desc" ? " ▼" : ""}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => {
              const expanded = row.original.id === selectedId;
              return (
                <Fragment key={row.id}>
                  <tr
                    className={expanded ? "row sel" : "row"}
                    onClick={() => onSelect(row.original.id)}
                  >
                    {row.getVisibleCells().map((cell) => {
                      const numeric = (cell.column.columnDef.meta as { numeric?: boolean })
                        ?.numeric;
                      return (
                        <td key={cell.id} className={numeric ? "num" : undefined}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      );
                    })}
                  </tr>
                  {expanded && renderExpanded ? (
                    <tr className="expand">
                      <td colSpan={table.getVisibleLeafColumns().length}>
                        {/* Sticky keeps it at the left edge while the columns
                            scroll past; the measured width keeps it inside the
                            card instead of inheriting the table's. */}
                        <div className="expandInner" style={{ width: viewport }}>
                          {renderExpanded(row.original)}
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {table.getFilteredRowModel().rows.length === 0 ? (
        <div className="note">Nothing matches “{filter}”.</div>
      ) : null}
    </>
  );
}
