import { useTraining } from "../api/client";
import type { TrainingEntry, TrainingStage } from "../api/types";

/** Seconds as something readable at a glance, matching crowgpt's own _clock. */
function clock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 90) return `${Math.round(seconds)}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

const MARKS: Record<TrainingStage["status"], string> = {
  waiting: "○",
  running: "▶",
  done: "✓",
  FAILED: "✗",
};

function StageRow({ stage }: { stage: TrainingStage }) {
  const fraction =
    stage.total && stage.done ? Math.min(1, stage.done / stage.total) : null;
  return (
    <li className={`train-stage train-${stage.status.toLowerCase()}`}>
      <span className="train-mark">{MARKS[stage.status]}</span>
      <span className="train-name">{stage.name}</span>
      <span className="train-bar" aria-hidden={fraction === null}>
        {fraction !== null ? (
          <span className="train-fill" style={{ width: `${fraction * 100}%` }} />
        ) : null}
      </span>
      <span className="train-pct">
        {fraction !== null ? `${Math.round(fraction * 100)}%` : ""}
      </span>
      <span className="train-note">
        {stage.status === "done" && stage.took_seconds !== null
          ? `took ${clock(stage.took_seconds)}`
          : stage.note}
      </span>
    </li>
  );
}

function RunCard({ entry }: { entry: TrainingEntry }) {
  const run = entry.run;
  return (
    <div className="train-run">
      <div className="train-head">
        <h3>{run.title}</h3>
        <p className="train-sub">
          {run.failed
            ? "failed"
            : run.finished
              ? "finished"
              : entry.stale
                ? "not writing — stopped, crashed or killed"
                : `running · ${clock(run.eta_seconds)} left`}
          {" · "}
          {clock(run.elapsed_seconds)} elapsed · updated {clock(entry.age_seconds)} ago
        </p>
      </div>
      <ul className="train-stages">
        {run.stages.map((stage) => (
          <StageRow key={stage.name} stage={stage} />
        ))}
      </ul>
      {run.notes.length ? (
        <pre className="train-notes">{run.notes.join("\n")}</pre>
      ) : null}
    </div>
  );
}

/** One line for a run that is over — the recent story without the archive. */
function DoneRow({ entry }: { entry: TrainingEntry }) {
  const run = entry.run;
  const outcome = run.failed
    ? "failed"
    : run.finished
      ? "finished"
      : "stopped";
  return (
    <li className={`train-over-row${run.failed ? " train-over-failed" : ""}`}>
      <span className="train-over-title">{run.title}</span>
      <span className="muted">
        {" — "}
        {outcome} · updated {clock(entry.age_seconds)} ago
      </span>
    </li>
  );
}

/**
 * What the long-running jobs are doing, read off the files they write as they
 * go — one file per run, so a corpus scan and a finetune report side by side
 * instead of overwriting each other, which a single shared file once let them
 * do.
 *
 * Nothing is pushed here. A run is a separate process in a separate venv,
 * often under systemd, and requiring this server to be up before it could
 * make progress would be the wrong dependency in the wrong direction — the
 * run matters, the dashboard is a window onto it.
 *
 * Active runs get the full card; finished and silent ones collapse to a line
 * each, because the question this panel answers is "what is happening now".
 */
export function TrainingPanel({ signedIn }: { signedIn: boolean }) {
  const training = useTraining(signedIn);
  const status = training.data;

  if (training.isLoading) return <p className="muted">Reading…</p>;
  if (!status || !status.runs.length) {
    return (
      <div className="panel">
        <h2>Progress Monitor</h2>
        <p className="muted">
          Nothing running. Long jobs write their progress to{" "}
          <code>{status?.dir ?? "data/progress/"}</code> as they go, one file
          per run, and this reads them — start one and it appears here.
        </p>
      </div>
    );
  }

  const live = status.runs.filter((r) => r.active);
  const over = status.runs.filter((r) => !r.active);
  return (
    <div className="panel">
      <h2>Progress Monitor</h2>
      {live.map((entry) => (
        <RunCard key={entry.slug} entry={entry} />
      ))}
      {!live.length ? (
        <p className="muted">Nothing running right now — recent runs below.</p>
      ) : null}
      {over.length ? (
        <ul className="train-over">
          {over.map((entry) => (
            <DoneRow key={entry.slug} entry={entry} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
