/**
 * The root component.
 *
 * Not the entry point — that is index.ts, which calls registerRootComponent on
 * this. The two are one line each and easy to mistake for one another.
 *
 * The Phase 0 rig that used to live here answered its questions and has become
 * `src/ui/DiagnosticsScreen.tsx` — its mic-source probe is still how an
 * unfamiliar handset gets checked, so it is reachable from Settings rather than
 * deleted.
 */
export { CrowGPTApp as default } from "./src/app/CrowGPTApp";
