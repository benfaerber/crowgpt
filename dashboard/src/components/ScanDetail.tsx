import { useEffect, useRef, useState } from "react";

import { PhotoReading } from "../../../shared/scan";
import { fetchScanContributionUrl, useScanContribution } from "../api/client";
import type {
  DetectedCall,
  FleetConfig,
  PhotoResult,
  ScanContext,
  ScanContribution,
  ScanContributionDetail,
  ScanLabel,
  SoundResult,
} from "../api/types";
import { formatBytes, formatCoords, formatTime } from "../format";
import { colorForCall, colorForContext, contextText, labelText } from "../vocab";
import { DetectedCalls } from "./DetectedCalls";
import { Fact, Pill } from "./detail-atoms";
import { PhotoFrame, PhotoHeadline, SpeciesRanking } from "./photo-reading";
import { Waveform } from "./Waveform";

/**
 * Everything the server holds about one kept scan: the file, the scanner's
 * whole answer, and whatever its visitor said at the labelling desk.
 *
 * The row in the pile is a line of this. Nothing is left out here on the
 * grounds that it is uninteresting, because the operator's question when
 * opening one is "should this become a capture", and the answer can turn on
 * any of it: where it came from, whether the species filter was on, how sure
 * the detector was that there was a bird at all.
 */
export function ScanDetail({
  row,
  config,
}: {
  row: ScanContribution;
  config: FleetConfig | undefined;
}) {
  const detail = useScanContribution(row.id);
  const file = useKeptFile(row.id);

  if (detail.isPending) return <div className="muted">Loading…</div>;
  if (!detail.data) return <div className="muted">Could not load this scan.</div>;
  const scan = detail.data;

  return (
    <div className="scan-detail">
      {file.error ? <div className="note">Could not load the file — {file.error}</div> : null}
      {scan.kind === "photo" ? (
        <PhotoScan scan={scan} url={file.url} />
      ) : (
        <SoundScan scan={scan} url={file.url} config={config} />
      )}
    </div>
  );
}

function PhotoScan({ scan, url }: { scan: ScanContributionDetail; url: string | undefined }) {
  const result = scan.result as PhotoResult | null;
  const reading = result ? new PhotoReading(result) : undefined;
  return (
    <div className="scan-detail-top">
      {url ? (
        <PhotoFrame url={url} alt={`kept scan ${scan.id}`} reading={reading} />
      ) : (
        <div className="scan-media-wait muted">loading the photo…</div>
      )}
      <div className="photo-id-answer">
        {reading ? (
          <>
            <PhotoHeadline reading={reading} />
            <SpeciesRanking reading={reading} />
          </>
        ) : (
          <span className="muted">The scan stored no result.</span>
        )}
        <dl className="facts">
          <FileFacts scan={scan} />
          {reading ? <PhotoFacts reading={reading} /> : null}
        </dl>
      </div>
    </div>
  );
}

function PhotoFacts({ reading }: { reading: PhotoReading }) {
  const { result } = reading;
  const box = result.bird_box;
  const source = result.location_source === "exif" ? "the photo's GPS tags" : "the visitor's location";
  return (
    <>
      <Fact label="Frame">
        {result.width} × {result.height} px
      </Fact>
      <Fact label="Birds found">
        {box ? (
          <>
            {box.birds}
            {box.birds > 1 ? " · the largest was judged" : ""}
            {box.score != null ? (
              <span className="muted"> · detector {box.score.toFixed(2)}</span>
            ) : null}
          </>
        ) : (
          <span className="muted">none, so the ranking describes the whole photo</span>
        )}
      </Fact>
      <Fact label="Location">
        {result.used_location ? (
          <>
            {reading.place()} <span className="muted">· from {source}, used to rule species in and out</span>
          </>
        ) : reading.located ? (
          <>
            {reading.place()}{" "}
            <span className="muted">· from {source}, ignored: none of the species is recorded near there</span>
          </>
        ) : (
          <span className="muted">none, judged on the picture alone</span>
        )}
      </Fact>
    </>
  );
}

function SoundScan({
  scan,
  url,
  config,
}: {
  scan: ScanContributionDetail;
  url: string | undefined;
  config: FleetConfig | undefined;
}) {
  const result = scan.result as SoundResult | null;
  const player = useRef<HTMLMediaElement | null>(null);
  const [position, setPosition] = useState<number>();
  const duration = result?.duration_sec ?? 0;

  const seek = (seconds: number) => {
    if (!player.current) return;
    player.current.currentTime = seconds;
    void player.current.play();
  };
  const follow = (event: React.SyntheticEvent<HTMLMediaElement>) =>
    setPosition(event.currentTarget.currentTime);

  const facts = (
    <dl className="facts">
      <FileFacts scan={scan} />
      <Fact label="Length">
        {scan.duration_sec != null ? `${scan.duration_sec.toFixed(1)} s` : "—"}
        {scan.truncated ? (
          <span className="muted"> · longer than the scanner reads; only this much was heard</span>
        ) : null}
      </Fact>
      <Fact label="Species filter">
        {result?.located ? (
          "limited to species found near the visitor"
        ) : (
          <span className="muted">off, so the species is the model&apos;s unfiltered guess</span>
        )}
      </Fact>
    </dl>
  );

  return (
    <>
      {scan.kind === "video" ? (
        <div className="scan-detail-top">
          {url ? (
            <video
              ref={player as React.RefObject<HTMLVideoElement>}
              controls
              src={url}
              onTimeUpdate={follow}
              onSeeked={follow}
            />
          ) : (
            <div className="scan-media-wait muted">loading the video…</div>
          )}
          {facts}
        </div>
      ) : (
        <>
          {facts}
          {url ? (
            <audio
              ref={player as React.RefObject<HTMLAudioElement>}
              controls
              src={url}
              onTimeUpdate={follow}
              onSeeked={follow}
            />
          ) : null}
        </>
      )}

      {result && duration > 0 ? (
        <Waveform
          peaks={result.waveform ?? []}
          calls={scan.calls}
          duration={duration}
          position={position}
          colorFor={(callType) => colorForCall(config, callType)}
          onSeek={seek}
        />
      ) : null}

      <section>
        <DetectedCalls
          analysis={{ capture_id: 0, calls: scan.calls, co_detections: result?.co_detections }}
          config={config}
        />
      </section>

      <VisitorAnswers scan={scan} config={config} onSeek={seek} />
    </>
  );
}

/** What is true of the file whatever is in it. */
function FileFacts({ scan }: { scan: ScanContributionDetail }) {
  return (
    <>
      <Fact label="Scan">
        #{scan.id} <span className="muted">· kept {formatTime(scan.created_at)}</span>
      </Fact>
      <Fact label="From">{scan.requester_ip ?? <span className="muted">not recorded</span>}</Fact>
      <Fact label="File">
        {scan.format.toUpperCase()} {scan.kind} · {formatBytes(scan.bytes)}
        <span className="muted"> · {scan.storage_ref}</span>
      </Fact>
      <Fact label="Visitor was">
        {scan.latitude != null ? (
          <>
            {formatCoords(scan.latitude, scan.longitude, 3)}
            <span className="muted"> · approximate, as the page sent it</span>
          </>
        ) : (
          <span className="muted">no location sent</span>
        )}
      </Fact>
      <Fact label="Promoted">
        {scan.promoted_capture_id !== null ? (
          `capture ${scan.promoted_capture_id}`
        ) : (
          <span className="muted">not yet</span>
        )}
      </Fact>
      {scan.desk_url ? (
        <Fact label="Visitor's link">
          <a href={scan.desk_url}>{scan.desk_url}</a>
        </Fact>
      ) : null}
    </>
  );
}

function VisitorAnswers({
  scan,
  config,
  onSeek,
}: {
  scan: ScanContributionDetail;
  config: FleetConfig | undefined;
  onSeek: (seconds: number) => void;
}) {
  const { labels, context, calls } = scan;
  const wholeRecording = context.filter((event) => event.label_uuid === null);
  const rows = spans(calls, labels);
  const said = labels.length > 0 || context.length > 0 || scan.silent_confirmed_at !== null;

  return (
    <section>
      <h2>
        Visitor said {said ? null : <span className="muted">(nothing yet)</span>}
      </h2>
      {scan.silent_confirmed_at ? (
        <div className="note">
          <strong>No calls in it</strong> — the visitor listened and said so, on{" "}
          {formatTime(scan.silent_confirmed_at)}.
        </div>
      ) : null}
      {wholeRecording.length ? (
        <div className="scan-whole">
          <span className="muted">During the whole recording</span>
          <ContextPills events={wholeRecording} config={config} />
        </div>
      ) : null}
      {labels.length ? (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Span</th>
                <th>Scanner</th>
                <th>Visitor</th>
                <th>Caller</th>
                <th>Context</th>
                <th>Labelled</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((span) => (
                <tr key={`${span.start}-${span.end}-${span.label?.client_uuid ?? "scanner"}`}>
                  <td>
                    <button
                      className="ghost scan-seek"
                      title="Play from here"
                      onClick={() => onSeek(Math.max(0, span.start - 1))}
                    >
                      {span.start.toFixed(1)}–{span.end.toFixed(1)} s
                    </button>
                  </td>
                  <td>
                    <CallPill callType={span.heard} config={config} />
                  </td>
                  <td>
                    <CallPill callType={span.label?.call_type} config={config} />
                    {span.label && !span.label.from_detection ? (
                      <span className="muted" title="A span the visitor marked, not one the scanner found">
                        {" "}· own span
                      </span>
                    ) : null}
                  </td>
                  <td>{span.label?.caller_role ?? <span className="muted">—</span>}</td>
                  <td>
                    {span.label ? (
                      <ContextPills
                        events={context.filter((event) => event.label_uuid === span.label?.client_uuid)}
                        config={config}
                      />
                    ) : null}
                  </td>
                  <td className="muted">{span.label ? formatTime(span.label.created_at) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function CallPill({
  callType,
  config,
}: {
  callType: string | null | undefined;
  config: FleetConfig | undefined;
}) {
  if (!callType) return <span className="muted">—</span>;
  return <Pill color={colorForCall(config, callType)}>{labelText(config, callType)}</Pill>;
}

function ContextPills({ events, config }: { events: ScanContext[]; config: FleetConfig | undefined }) {
  if (events.length === 0) return <span className="muted">—</span>;
  return (
    <div className="pills">
      {events.map((event) => (
        <Pill key={event.client_uuid} color={colorForContext(config, event.key)}>
          {contextText(config, event.key)}
        </Pill>
      ))}
    </div>
  );
}

interface Span {
  start: number;
  end: number;
  heard?: string | null;
  label?: ScanLabel;
}

/** Every detection with the label on the same span beside it, then labels on spans of their own. */
function spans(calls: DetectedCall[], labels: ScanLabel[]): Span[] {
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
