import type { Dictation } from "../api/types";
import { formatTime } from "../format";

/** Spoken field notes, transcribed by a machine — his words, its spelling. */
export function Dictations({ dictations }: { dictations: Dictation[] }) {
  if (dictations.length === 0) return null;
  return (
    <>
      {/* Below "what a model wrote" and above the recordist's own words,
          because that is exactly where it sits: these ARE his words, read
          back by a machine that cannot spell a crow's name. Placing it
          above the observations would let an unchecked transcript wear the
          authority of something he typed. */}
      <h2 style={{ marginTop: "1.2rem" }}>What the recordist said out loud</h2>
      <div className="note">
        Spoken in the field and transcribed by a machine. The words are his;
        the spelling is a guess. Not testimony until somebody has listened
        and confirmed it — names, numbers and species are exactly what a
        transcript gets wrong.
      </div>
      {dictations.map((note) => (
        <div className="obs" key={note.id}>
          {note.transcript ?? <em>not transcribed yet</em>}
          <div className="meta">
            {note.duration_sec ? `${Math.round(note.duration_sec)}s · ` : ""}
            {note.confirmed_at
              ? `confirmed ${formatTime(note.confirmed_at)} — also under Observations`
              : "unconfirmed"}
            {note.transcript_model ? ` · ${note.transcript_model}` : ""}
            {note.mean_logprob !== null
              ? ` · mean logprob ${note.mean_logprob.toFixed(2)}`
              : ""}
          </div>
        </div>
      ))}
    </>
  );
}
