/**
 * The figures on the page, read from promo/stats.json.
 *
 * The HTML gets its numbers substituted at build time by the `{{key}}` plugin
 * in vite.config.ts; this is the same file for the parts built in script — the
 * chart, mainly, where a number is a bar length as well as a caption.
 *
 * The import is bundled, so this still costs no request. `stats.json` is
 * refreshed by promo/tools/build_stats.py, which is the only thing that should
 * be editing the auto figures.
 */

import document from "../stats.json";

/** A context chip: what a recordist can say they saw while a call was made. */
export interface Tag {
  key: string;
  category: string;
  label: string;
  used: number;
}

interface Figure {
  value: number | string | Tag[];
  text: string;
  about: string;
  source: string;
  auto?: boolean;
}

const FIGURES = document.figures as Record<string, Figure>;

function figure(key: string): Figure {
  const found = FIGURES[key];
  // Typecheck cannot reach these — the keys are strings, and stats.json is data
  // that a refresh could rename. Failing loudly beats a bar of length NaN.
  if (!found) throw new Error(`no figure "${key}" in stats.json`);
  return found;
}

/** What the page prints — already grouped and rounded by the refresher. */
export function text(key: string): string {
  return figure(key).text;
}

/** The raw measurement, for anything that has to compute with it. */
export function num(key: string): number {
  const { value } = figure(key);
  if (typeof value !== "number") throw new Error(`figure "${key}" is not a number`);
  return value;
}

/**
 * The context vocabulary, grouped the way the app groups it.
 *
 * A figure whose value is a list rather than a number — the prose form is in
 * its `text`, and this is for anything that wants to lay the chips out.
 */
export function tags(key = "context.vocabulary"): Tag[] {
  const { value } = figure(key);
  if (!Array.isArray(value)) throw new Error(`figure "${key}" is not a list`);
  return value;
}
