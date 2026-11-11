/**
 * The upload policy, and whether this account has answered it.
 *
 * Consent is per account and given once, during onboarding, before anything
 * syncs. The policy text and its version come from the server, so the phone
 * never decides which version is current; it only knows which one this account
 * accepted, from the identity the server last returned.
 */

export interface UploadPolicy {
  version: number;
  title: string;
  /** Markdown, as the server stores it. */
  text: string;
}

export interface ConsentAnswers {
  allowGenerator: boolean;
  allowPublish: boolean;
}

export interface ConsentState {
  /** The version accepted, or undefined for an account that never saw one. */
  policyVersion?: number;
  allowGenerator?: boolean;
  allowPublish?: boolean;
}

/**
 * Whether onboarding should run.
 *
 * Without the current version in hand (offline at first launch) an account
 * that has accepted *some* version is let through: the server refuses nothing
 * on an old version, and stopping a recordist at the door over a wording
 * change they cannot download yet would cost a morning's fieldwork for no one's
 * benefit. An account that has accepted none is always asked.
 */
export function needsConsent(state: ConsentState | undefined, currentVersion?: number): boolean {
  if (state?.policyVersion === undefined) return true;
  if (currentVersion === undefined) return false;
  return state.policyVersion < currentVersion;
}

/** Why syncing must wait, or nothing. */
export function consentBlocksSync(state: ConsentState | undefined): string | undefined {
  return state?.policyVersion === undefined
    ? "Accept the upload policy first — nothing is sent until you have."
    : undefined;
}

/** The answers as a sentence, for Settings. */
export function describeConsent(state: ConsentState | undefined): string {
  if (state?.policyVersion === undefined) return "Not accepted yet";
  const generator = state.allowGenerator === false ? "not the generator" : "the generator";
  const publish = state.allowPublish ? "may be published" : "never published";
  return `Policy v${state.policyVersion} · CawDex, Crow Translate, ${generator} · ${publish}`;
}

/** One block of the policy's markdown, for a renderer with no markdown library. */
export type PolicyBlock =
  | { kind: "heading"; level: number; text: string }
  | { kind: "bullet"; text: string; ordinal?: number }
  | { kind: "paragraph"; text: string };

/**
 * The subset of markdown the policy uses: headings, bullets, numbered items,
 * paragraphs. Bold markers are left for the renderer to split. A dependency for
 * one screen of text would be a native-module risk with no upside.
 */
export function parsePolicy(markdown: string): PolicyBlock[] {
  const blocks: PolicyBlock[] = [];
  let paragraph: string[] = [];
  let item: PolicyBlock | undefined;
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    if (item) blocks.push(item);
    paragraph = [];
    item = undefined;
  };
  for (const raw of markdown.split("\n")) {
    const line = raw.trim();
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    const numbered = /^(\d+)\.\s+(.*)$/.exec(line);
    if (!line) {
      flush();
    } else if (heading) {
      flush();
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
    } else if (bullet) {
      flush();
      item = { kind: "bullet", text: bullet[1] };
    } else if (numbered) {
      flush();
      item = { kind: "bullet", text: numbered[2], ordinal: Number(numbered[1]) };
    } else if (item && item.kind === "bullet") {
      item = { ...item, text: `${item.text} ${line}` };
    } else {
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}

/** Split `**bold**` runs out of a line. */
export function boldRuns(text: string): { text: string; bold: boolean }[] {
  return text
    .split(/(\*\*[^*]+\*\*)/)
    .filter((part) => part.length > 0)
    .map((part) =>
      part.startsWith("**") && part.endsWith("**")
        ? { text: part.slice(2, -2), bold: true }
        : { text: part.replace(/\*([^*]+)\*/g, "$1"), bold: false });
}
