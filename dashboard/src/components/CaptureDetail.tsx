import { useCaptureDetail, useFleetConfig } from "../api/client";
import {
  describeOffset,
  describePlaceForOperator,
  formatTime,
} from "../format";
import { distanceLabel, observerRoleText } from "../vocab";
import { AiDescriptions } from "./AiDescriptions";
import { AudioPanel } from "./AudioPanel";
import { DetectedCalls } from "./DetectedCalls";
import { Dictations } from "./Dictations";
import { Fact } from "./detail-atoms";
import { LabelList } from "./LabelList";
import { SnrGauge } from "./SnrGauge";
import { StatusPill } from "./StatusPill";

export function CaptureDetail({
  captureId,
  inline = false,
}: {
  captureId: number;
  /**
   * Drawn inside a table row rather than as a card of its own.
   *
   * Only the outer frame differs. A card nested in a card reads as a second
   * panel that happens to be indented, which is the opposite of what expanding
   * a row is meant to say.
   */
  inline?: boolean;
}) {
  const { data, isPending, error } = useCaptureDetail(captureId);
  // The served vocabulary, for the words and colours the phone uses. Cached by
  // the query client and shared with AudioPanel, so this costs no extra fetch.
  const config = useFleetConfig().data;
  const frame = inline ? "detail" : "card";

  if (isPending) return <div className={`${frame} muted`}>Loading…</div>;
  if (error) {
    return (
      <div className={frame}>
        <div className="note">Failed to load — {error.message}</div>
      </div>
    );
  }

  const {
    capture, media, analysis, quality, labels, observations, sightings,
    context, ai_descriptions: written, dictations,
  } = data;
  // Audio first, then video — mirroring what the server picks to analyze. A
  // capture that is only video is what a dashboard upload of a test clip looks
  // like, and it played nothing at all while claiming "no audio".
  const complete = media.filter((m) => m.upload_state === "complete");
  const audio =
    complete.find((m) => m.kind === "audio") ?? complete.find((m) => m.kind === "video");

  return (
    <div className={frame}>
      <h2>
        {capture.name ?? `Capture #${capture.id}`}
        <span className="muted"> · {capture.contributor_name ?? "—"}</span> ·{" "}
        <StatusPill status={capture.status} />
      </h2>
      <div className="muted" style={{ fontSize: ".82rem" }}>
        #{capture.id} · {formatTime(capture.recorded_at ?? capture.created_at)}
      </div>

      {/* Everything the recording knows about itself, in one block rather than
          scattered down the card. Most of it was only ever visible as a column
          in the list, which meant opening a capture told you less about it than
          scrolling past it did. */}
      <dl className="facts">
        <Fact label="Kept">
          {capture.keep
            ? <span title="marked a real observation">★ real observation</span>
            : <span className="muted">· seeded or test material</span>}
        </Fact>
        <Fact label="Known as">
          {capture.observer_role
            ? observerRoleText(config, capture.observer_role)
            : <span className="muted">not said</span>}
        </Fact>
        <Fact label="Where">{describePlaceForOperator(capture)}</Fact>
        {capture.region ? <Fact label="Region">{capture.region}</Fact> : null}
        <Fact label="Phone">
          {capture.device_label ?? <span className="muted">—</span>}
          {capture.app_version ? (
            <span className="muted"> · app v{capture.app_version}</span>
          ) : null}
        </Fact>
        {capture.family_id !== null ? (
          <Fact label="Family">#{capture.family_id}</Fact>
        ) : null}
      </dl>

      {/* The denominator of the whole project: a recording somebody listened to
          and confirmed held nothing. Without it the matrix cannot say how often
          the same situation happened and the crows said nothing — so an unshown
          silent mark is indistinguishable from an unanalysed capture. */}
      {capture.silent_confirmed_at ? (
        <div className="note" style={{ marginTop: ".6rem" }}>
          <strong>Confirmed silent</strong> — a human listened and marked no crow
          calls, on {formatTime(capture.silent_confirmed_at)}. This is evidence,
          not an absence of it: it is the control the calls × context matrix
          counts against. A label landing here clears the mark automatically.
        </div>
      ) : null}

      {capture.notes ? <div className="note">{capture.notes}</div> : null}

      {audio ? (
        <AudioPanel
          audio={audio}
          analysis={analysis}
          fallbackDuration={capture.duration_sec}
        />
      ) : (
        <div className="note">Nothing fully uploaded yet.</div>
      )}

      {/* Every other slot. One capture can hold audio and video, and showing
          only the one the analyzer picked meant a half-uploaded second file was
          invisible on the page you would go to in order to find it. */}
      {media.filter((m) => m !== audio).length > 0 ? (
        <div className="note" style={{ marginTop: ".6rem" }}>
          Also on this capture:{" "}
          {media
            .filter((m) => m !== audio)
            .map((m) =>
              `${m.kind} (${m.format}, ${m.upload_state}`
              + `${m.pre_roll_sec ? `, ${m.pre_roll_sec}s pre-roll` : ""})`)
            .join(", ")}
          .
        </div>
      ) : null}

      {quality ? (
        // Measurements, not judgements — the same axis every experiment quotes
        // (0004: ~2.5 dB of band SNR is ~0.19 of BirdNET confidence). Rendered
        // with the audio rather than with the analysis: it describes the
        // recording, not what the model made of it.
        <div className="note" style={{ marginTop: ".8rem" }}>
          <SnrGauge db={quality.band_snr_db} /> Band SNR{" "}
          <strong>
            {quality.band_snr_db == null
              ? "unmeasurable (digital silence in the quiet percentile)"
              : `${quality.band_snr_db.toFixed(1)} dB`}
          </strong>{" "}
          · noise
          floor {quality.noise_floor_band_dbfs.toFixed(1)} dBFS in the crow band
          ({quality.noise_floor_low_dbfs.toFixed(1)} below 300 Hz) · peak{" "}
          {quality.peak_dbfs.toFixed(1)} / RMS {quality.rms_dbfs.toFixed(1)} dBFS ·{" "}
          {quality.clip_events === 0
            ? "no clipping"
            : `${quality.clip_events} clip event${quality.clip_events === 1 ? "" : "s"} (${quality.clipped_samples} samples)`}
        </div>
      ) : null}

      <DetectedCalls analysis={analysis} config={config} />

      <AiDescriptions written={written} />

      <LabelList
        labels={labels}
        context={context}
        config={config}
        silentConfirmedAt={capture.silent_confirmed_at}
      />

      {capture.crop_start_sec !== null && capture.crop_end_sec !== null ? (
        // Stated wherever the duration is, or the duration reads as the length
        // of the file — which for a trimmed capture it is not.
        <div className="note" style={{ marginTop: ".8rem" }}>
          Trimmed before upload: the stored audio is{" "}
          {(capture.crop_end_sec - capture.crop_start_sec).toFixed(1)}s from{" "}
          {capture.crop_start_sec.toFixed(1)}s of a{" "}
          {capture.duration_sec?.toFixed(1) ?? "?"}s recording.
        </div>
      ) : null}

      {capture.adult_count !== null || capture.juvenile_count !== null
        || capture.unaged_count !== null ? (
        <div className="note" style={{ marginTop: ".8rem" }}>
          Seen:{" "}
          {[
            capture.adult_count !== null ? `${capture.adult_count} adult` : null,
            capture.juvenile_count !== null ? `${capture.juvenile_count} juvenile` : null,
            capture.unaged_count !== null ? `${capture.unaged_count} unaged` : null,
          ].filter(Boolean).join(", ")}
          . Unaged means seen but not close enough to age — not a guess.
        </div>
      ) : null}

      {capture.distance_band ? (
        <div className="note" style={{ marginTop: ".8rem" }}>
          Bird was <strong>{distanceLabel(capture.distance_band)}</strong>
          {" "}away. Signal-to-noise falls off with distance, so this is not a detail —
          it is the confound in any comparison across recordists or sites.
        </div>
      ) : null}

      {capture.behavior_guess ? (
        <>
          <h2 style={{ marginTop: "1.2rem" }}>What the recordist thinks it meant</h2>
          {/* Its own section, worded as a guess. A hypothesis rendered next to
              measurements starts being read as one. */}
          <div className="note" style={{ marginBottom: ".6rem" }}>
            A guess — excluded from training data and from the calls × context matrix.
          </div>
          <div className="obs">{capture.behavior_guess}</div>
        </>
      ) : null}

      {sightings && sightings.length > 0 ? (
        <>
          <h2 style={{ marginTop: "1.2rem" }}>Seen nearby, not during</h2>
          {/* Its own section, never folded in with context. These are leads —
              things noticed around the recording — and the calls x context
              matrix is deliberately blind to them. */}
          <div className="note" style={{ marginBottom: ".6rem" }}>
            Not ground truth — excluded from the calls × context matrix.
          </div>
          {sightings.map((sighting) => (
            <div className="obs" key={sighting.id}>
              {sighting.key.replace(/_/g, " ")}
              {sighting.notes ? ` — ${sighting.notes}` : ""}
              <div className="meta">
                {describeOffset(sighting.offset_sec)}
                {sighting.distance_m ? ` · ~${sighting.distance_m} m away` : ""}
              </div>
            </div>
          ))}
        </>
      ) : null}

      <Dictations dictations={dictations} />

      {observations.length > 0 ? (
        <>
          <h2 style={{ marginTop: "1.2rem" }}>Observations</h2>
          {observations.map((observation) => (
            <div className="obs" key={observation.id}>
              {observation.body}
              <div className="meta">
                {formatTime(observation.created_at)} · {observation.source}
              </div>
            </div>
          ))}
        </>
      ) : null}
    </div>
  );
}
