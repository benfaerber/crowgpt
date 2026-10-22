/**
 * The fleet's served vocabulary.
 *
 * Labels are the operator's to define, not the app's: promoting a recurring
 * phrase to a tag is a config push, not an app release. The phone therefore
 * asks what the vocabulary is rather than shipping one, and caches the answer —
 * a recordist in a field with no signal still needs to label what they just
 * heard.
 */
export interface LabelDef {
  /** Stable key, sent to the server. Never shown to the user. */
  key: string;
  /** The CORE class this trains into: alarm call / begging / call / flight call / song. */
  core: string;
  /** Localized display text. */
  text: string;
}

/** A witnessed situation — the other axis. See domain/context.ts. */
export interface ContextDef {
  key: string;
  /** threat / food / social / baseline — how the field UI groups the chips. */
  category: string;
  text: string;
}

export interface FleetConfig {
  version: number;
  locale: string;
  core_classes: string[];
  /** One colour per core class; every label inherits its core's. */
  core_colors: Record<string, string>;
  labels: LabelDef[];
  contexts: ContextDef[];
  /**
   * What the recordist was to these birds — see `captures.observerRole`.
   *
   * Served rather than hardcoded so the list can change without a rebuild, and
   * so the phone and the dashboard cannot disagree about what "feeder" means.
   */
  observer_roles: { key: string; text: string }[];
  /**
   * Which bird made a call — see `labels.caller_role`.
   *
   * Standing in the family rather than identity, because individuals need bands
   * and there are none. Served for the same reason as the roles above: the list
   * will change as the family does, and a phone that needs reinstalling to
   * learn a new one will keep offering the old.
   */
  caller_roles: { key: string; text: string }[];
  instructions: { key: string; text: string }[];
  /**
   * The field guide, served rather than shipped.
   *
   * What counts as a good recording is still being worked out, and a phone that
   * needs reinstalling to learn a better answer will keep giving the old one.
   * `part` splits using the app from reading the birds — a minute to learn
   * against a season.
   */
  guide: { key: string; part: string; title: string; body: string }[];
  taxonomy: { common_name: string; name: string; slug: string }[];
}

/**
 * What the app falls back to before it has ever reached the server.
 *
 * Deliberately the CORE classes only. A phone that has never synced can still
 * label the things every model head knows about, and the richer
 * operator-defined vocabulary arrives with the first config fetch — rather than
 * the app pretending to know a label set it has not been told.
 *
 * Mirrors fieldserver's CORE_CLASSES / CORE_COLORS.
 */
export const FALLBACK_CONFIG: FleetConfig = {
  version: 0,
  locale: "en",
  core_classes: ["alarm call", "begging", "call", "flight call", "song"],
  core_colors: {
    "alarm call": "#f27070",
    begging: "#efb057",
    call: "#6ea8fe",
    "flight call": "#6bd28a",
    song: "#c58af9",
  },
  labels: [
    { key: "alarm call", core: "alarm call", text: "Alarm call" },
    { key: "begging", core: "begging", text: "Begging" },
    { key: "call", core: "call", text: "Call" },
    { key: "flight call", core: "flight call", text: "Flight call" },
    { key: "song", core: "song", text: "Song" },
  ],
  // Empty until the first fetch: unlike call types, there is no defensible
  // guess at what situations an operator cares about, and a phone offering
  // invented ones would put keys in the corpus the server has never heard of.
  contexts: [],
  observer_roles: [],
  // Empty until fetched, like contexts and for the same reason: an invented
  // caller role would put a key in the corpus the server has never heard of,
  // and on the one field that is supposed to be a person's direct testimony.
  caller_roles: [],
  instructions: [],
  guide: [],
  taxonomy: [],
};

const UNTYPED = "#9aa5b1";

/**
 * The colour for a call type, resolved through its core class.
 *
 * So "mobbing" reads as the alarm it maps to, and a label the operator adds
 * later is coloured without anyone choosing one for it. Anything unrecognised
 * stays grey rather than borrowing another type's colour and implying a
 * classification we don't have.
 */
export function colorForCall(config: FleetConfig, callType?: string | null): string {
  if (!callType) return UNTYPED;
  const core = config.labels.find((label) => label.key === callType)?.core ?? callType;
  return config.core_colors[core] ?? UNTYPED;
}

export function labelText(config: FleetConfig, callType?: string | null): string {
  if (!callType) return "unlabelled";
  return config.labels.find((label) => label.key === callType)?.text ?? callType;
}
