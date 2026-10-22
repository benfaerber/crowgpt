import { useEffect, useState } from "react";

import { useListening } from "../api/client";
import type { ListeningPool } from "../api/types";

/**
 * How much grading is left, and whether a dose is ready — nothing else.
 *
 * NO SCORE IS SHOWN, AND THAT IS DELIBERATE. The server refuses any per-arm
 * result until the pool's pre-committed trial count is answered, because a panel
 * you glance at between doses is exactly where a sitting gets stopped the moment
 * it looks resolved. That is optional stopping, and it takes a nominal 5% test to
 * 20-30%. This panel therefore has no number in it that could be read as "which
 * arm is winning" — only counts and a clock.
 *
 * The clock counts down locally between polls. `useListening` refreshes every
 * 20 s, and a cooldown that only moved on those ticks reads as stuck; the
 * deadline is recomputed from the server's `locked_for` on every fetch, so a
 * backgrounded tab that stops firing timers is corrected rather than trusted.
 */
function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = whole % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return hours ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${minutes}:${pad(rest)}`;
}

function useCountdown(lockedFor: number): number {
  const [left, setLeft] = useState(lockedFor);

  useEffect(() => {
    setLeft(lockedFor);
    if (lockedFor <= 0) return;
    const deadline = Date.now() + lockedFor * 1000;
    const handle = setInterval(() => {
      setLeft(Math.max(0, (deadline - Date.now()) / 1000));
    }, 1000);
    return () => clearInterval(handle);
  }, [lockedFor]);

  return left;
}

function PoolRow({ pool }: { pool: ListeningPool }) {
  const left = useCountdown(pool.locked_for);
  const done = pool.trials ? pool.answered / pool.trials : 0;
  const finished = pool.remaining <= 0;
  const locked = left > 0 && !finished;

  return (
    <li className="listen-pool">
      <div className="listen-head">
        <span className="listen-name">{pool.name}</span>
        <span className="listen-count">
          {pool.answered} / {pool.trials}
        </span>
        {finished ? (
          <span className="listen-state">complete</span>
        ) : locked ? (
          <span
            className="listen-state listen-locked"
            title={`${pool.cooldown_minutes} minutes between doses`}
          >
            next dose in {clock(left)}
          </span>
        ) : (
          <span className="listen-state listen-ready">dose ready</span>
        )}
      </div>
      <span className="listen-bar">
        <span className="listen-fill" style={{ width: `${done * 100}%` }} />
      </span>
      <p className="listen-sub">
        {finished
          ? pool.can_reveal
            ? "every trial answered — results are readable"
            : "finished"
          : `${pool.remaining} left, ${pool.dose_size} at a time`}
        {pool.cooldown_minutes ? ` · ${pool.cooldown_minutes} min between doses` : ""}
      </p>
    </li>
  );
}

export function ListeningPanel({ signedIn }: { signedIn: boolean }) {
  const pools = useListening(signedIn);
  const open = (pools.data ?? []).filter((p) => !p.closed_at);

  // An empty roster is the normal state most weeks, so it gets a sentence rather
  // than an error — the same shape TrainingPanel uses for "no run on disk".
  if (!open.length) {
    return (
      <div className="card">
        <h2>Listening</h2>
        <p className="note">
          No pool to grade. Build one from an experiment with{" "}
          <code>crowgpt.pool</code>, then register it with{" "}
          <code>fieldserver/tools/register_pool.py</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>Listening</h2>
      <ul className="listen-pools">
        {open.map((pool) => (
          <PoolRow key={pool.id} pool={pool} />
        ))}
      </ul>
      {/* A plain anchor, not a nav button: /listen/ is served by fieldserver as
          its own page and is not part of this bundle, so routing to it in the SPA
          would 404 on reload. */}
      <p className="listen-go">
        <a href="/listen/">Grade a dose →</a>
      </p>
    </div>
  );
}
