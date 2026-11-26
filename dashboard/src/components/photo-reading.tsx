import { PhotoReading, percent } from "../../../shared/scan";

/** The photo with the bird the classifier judged outlined on it. */
export function PhotoFrame({
  url,
  alt,
  reading,
}: {
  url: string;
  alt: string;
  reading: PhotoReading | undefined;
}) {
  const box = reading?.box;
  return (
    <div className="photo-id-frame">
      <img src={url} alt={alt} />
      {box ? (
        <div className="photo-id-box" title="where the classifier found the bird" style={box} />
      ) : null}
    </div>
  );
}

/** The species the head ranked, as bars. All of them when `count` is omitted. */
export function SpeciesRanking({ reading, count }: { reading: PhotoReading; count?: number }) {
  const scores = count === undefined ? reading.result.ranking : reading.top(count);
  return (
    <div className="bars">
      {scores.map((score) => (
        <div className="bar" key={score.slug} title={score.scientific_name}>
          <div className="name">{score.common_name}</div>
          <div className="track">
            <div className="fill" style={{ width: `${score.probability * 100}%` }} />
          </div>
          <div className="v">{percent(score.probability)}</div>
        </div>
      ))}
    </div>
  );
}

/** What the photo is of, in the operator's words rather than the visitor's. */
export function PhotoHeadline({ reading }: { reading: PhotoReading }) {
  const best = reading.best;
  const closest = best?.common_name ?? "nothing it knows";
  return (
    <>
      <h3>
        {reading.verdict === "other"
          ? "Not a corvid"
          : reading.verdict === "no_bird"
            ? "No bird found"
            : closest}
      </h3>
      <span className="sci">
        {reading.verdict === "other"
          ? `The detector sees ${reading.instead} and no bird. The ranking is what the head says anyway.`
          : reading.verdict === "no_bird"
            ? `Closest match if there is a corvid in it: ${closest}.`
            : best?.scientific_name}
      </span>
    </>
  );
}
