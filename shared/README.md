# shared

TypeScript that the operator dashboard (`dashboard/`) and the promo site
(`promo/`) both compile in. Plain modules, imported by relative path: no
package, no build step of its own, no dependencies, no DOM and no React.

What belongs here is the part two pages must agree on: the shape of a
server answer and how to read it. How it is drawn stays with each page.

- `scan/` reads a scan's result: the photo worker's answer (`PhotoReading`),
  the sound worker's (`SoundResult`, `coDetectionLine`), and where things sit
  on a waveform (`TimelineGeometry`).

Both `tsconfig.json` files include this directory, so `make -C dashboard
typecheck` and `make -C promo typecheck` each check it under their own rules.
The dashboard's are the stricter (`verbatimModuleSyntax`, `noUnusedLocals`),
so write to those.
