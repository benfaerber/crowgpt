import type { Device } from "../api/types";
import { formatTime } from "../format";

/**
 * The actual handsets.
 *
 * The contributors panel answers "whose captures are these?", which is what
 * matters for a corpus, but it deliberately collapses a person's phones into one
 * row. "Which phone is this, and is it current?" is a real question too — an
 * unnamed device is usually one running a build old enough to predate naming.
 *
 * `App` is which build each handset last reported, stamped on every request it
 * makes. It is the column that answers "did the fix actually reach the phone?",
 * which nothing else here can.
 */
export function DevicesPanel({ devices }: { devices: Device[] }) {
  return (
    <div className="card">
      <h2>Devices</h2>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Device</th>
              <th>Owner</th>
              <th className="num">Captures</th>
              <th>App</th>
              <th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => (
              <tr key={device.id}>
                <td>
                  {device.label ?? (
                    <span className="muted">
                      unnamed {device.platform ?? "device"} #{device.id}
                    </span>
                  )}
                  {device.revoked_at ? <span className="muted"> · revoked</span> : null}
                </td>
                <td className="muted">
                  {device.display_name ?? "—"}
                </td>
                <td className="num">{device.capture_count}</td>
                {/* The build this phone last called in with. A fix committed and
                    never installed looks exactly like a fix that didn't work,
                    and nothing else on this dashboard can tell them apart. */}
                <td className={device.app_version ? undefined : "muted"}
                    title={device.app_commit ?? undefined}>
                  {device.app_version ? `v${device.app_version}` : "unknown"}
                </td>
                <td className="muted">{formatTime(device.last_seen_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
