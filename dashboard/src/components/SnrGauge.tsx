/**
 * Three bars gauging how hard a recording was to hear.
 *
 * An opinion, which the quality system itself refuses to hold — so the tiers
 * are pinned to experiment 0004's calibration rather than taste, and the
 * tooltip always carries the measured number. On that curve ~16 dB still
 * detects at ~0.9, and ~11 dB is under the 0.25 gate:
 *
 *   ≥15 dB   clear     detection has headroom
 *   12–15    marginal  sliding toward the gate
 *   <12      buried    below where BirdNET reliably fires
 *   null     unmeasurable — a merged capture's silence gaps leave no quiet
 *            signal to measure against; distinct from "not measured yet"
 */
export function SnrGauge({ db }: { db: number | null }) {
  const tier = db == null ? 0 : db >= 15 ? 3 : db >= 12 ? 2 : 1;
  const color =
    tier === 3 ? "var(--good)" : tier === 2 ? "var(--warn)" : "var(--bad)";
  const title =
    db == null
      ? "SNR unmeasurable — digital silence in the quiet percentile (merged capture)"
      : `band SNR ${db.toFixed(1)} dB — ${
          tier === 3 ? "clear" : tier === 2 ? "marginal" : "buried"
        }`;
  return (
    <svg
      viewBox="0 0 16 12"
      width={16}
      height={12}
      style={{ verticalAlign: "-.08em" }}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      {[0, 1, 2].map((bar) => (
        <rect
          key={bar}
          x={bar * 6}
          y={8 - bar * 4}
          width={4}
          height={4 + bar * 4}
          rx={1}
          fill={db != null && bar < tier ? color : "var(--border)"}
        />
      ))}
    </svg>
  );
}
