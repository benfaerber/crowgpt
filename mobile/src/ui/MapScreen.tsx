import { useEffect, useMemo, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View, Linking } from "react-native";

import { setBackInterceptor } from "../app/backInterceptor";
import { WebView } from "react-native-webview";

import type { AppServices } from "../app/AppServices";
import { useCaptures } from "../app/useCaptures";
import { log } from "../app/Log";
import type { CaptureRecord } from "../domain/types";
import type { ScoutVisit, VisitKind } from "../domain/scoutVisits";
import { mayShowCoords } from "../domain/location";
import type { Fix } from "../recording/LocationProvider";
import {
  applyView,
  DEFAULT_VIEW,
  describeView,
  type CaptureView,
} from "../domain/captureFilters";
import { CaptureFilterBar } from "./components/CaptureFilterBar";
import { labelQueue, needsLabelling } from "../domain/labelQueue";
import { buildMapHtml, mappableCaptures } from "./map/mapHtml";
import { useBrandTitleFont } from "./brandFont";
import { scoutingAdvice, type DayForecast } from "../domain/scoutingWindow";
import { fetchDayForecast } from "../net/openMeteo";
import { colors, radius, spacing } from "./theme";

export function MapScreen({
  services,
  view: filters,
  onViewChange: setFilters,
  focusUuid,
  onBack,
  onOpenCapture,
  onOpenSchedule,
}: {
  services: AppServices;
  /** Shared with the capture list — the same selection, drawn as pins. */
  view: CaptureView;
  onViewChange: (view: CaptureView) => void;
  /** Center on this capture instead of fitting them all. */
  focusUuid?: string;
  onBack: () => void;
  onOpenCapture: (capture: CaptureRecord) => void;
  onOpenSchedule: (forecast: DayForecast) => void;
}) {
  const { captures, labelCounts } = useCaptures(services);
  const [familyColors, setFamilyColors] = useState<Map<string, { color: string; name: string }>>(
    new Map(),
  );

  useEffect(() => {
    void services.families.list().then((families) =>
      setFamilyColors(new Map(families.map((f) => [f.uuid, { color: f.color, name: f.name }]))),
    );
  }, [services]);
  const [here, setHere] = useState<Fix | undefined>();

  // Asked for once when the map opens. A refused or slow fix simply means no
  // pin — the captures are the point, and the map must not wait on the GPS.
  useEffect(() => {
    let live = true;
    void services.location.current().then((fix) => {
      if (live) setHere(fix);
    });
    return () => {
      live = false;
    };
  }, [services]);
  // The queue narrows the map too, and has to: the view is shared with the
  // list, so a pill left on there would otherwise show a full map while the
  // list showed four rows — the same filter meaning two different things.
  const shown = useMemo(() => {
    const inView = applyView(captures, filters);
    return filters.unlabelledOnly ? labelQueue(inView, labelCounts) : inView;
  }, [captures, labelCounts, filters]);
  const precision = services.settings.locationPrecision;
  const censor = services.settings.censorCoords;
  const fuzzMiles = services.settings.fuzzMiles;
  const placed = useMemo(
    () => mappableCaptures(shown, familyColors, precision, censor, fuzzMiles),
    [shown, familyColors, precision, censor, fuzzMiles],
  );
  // Rebuilding the HTML reloads the WebView, so it is keyed on what actually
  // changes the map rather than on every render of the capture list.
  // Off by default: scouting is a mode, and 2,500 dots over the family's
  // pins is noise on an ordinary day. The toggle only exists when the server
  // has published a layer.
  const [showTrees, setShowTrees] = useState(services.settings.mapShowTrees);
  const treeLayer = services.trees;
  // Scouting is likewise a mode; the two layers toggle independently so a
  // scouting walk can show targets without 2,500 tree dots underneath.
  const [showScout, setShowScout] = useState(services.settings.mapShowScout);
  const scoutLayer = services.scout;
  const brandFont = useBrandTitleFont();

  /**
   * Is now a good time to be out at all? Sun-anchored and temp-scaled,
   * fetched by the phone itself — the advice matters precisely where the
   * field server isn't reachable. Valley weather is one weather; the fix
   * sharpens it when there is one, downtown stands in when there isn't.
   */
  const [advice, setAdvice] = useState<{ good: boolean; label: string }>();
  // Kept whole, not just the one-liner: tapping the advice opens the
  // hour-by-hour schedule page, which needs the day it was derived from.
  const forecastRef = useRef<DayForecast | undefined>(undefined);
  useEffect(() => {
    let live = true;
    void fetchDayForecast(
      here?.latitude ?? 40.7612,
      here?.longitude ?? -111.8826,
    ).then((forecast) => {
      if (live && forecast) {
        forecastRef.current = forecast;
        setAdvice(scoutingAdvice(forecast, new Date()));
      }
    });
    return () => {
      live = false;
    };
    // Deliberately not keyed on `here`: one forecast per map visit is plenty.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [familyHalos, setFamilyHalos] = useState(
    services.settings.mapFamilyHalos);
  const [hiddenSpecies, setHiddenSpecies] = useState<string[]>(
    services.settings.mapHiddenSpecies);
  // Refs, not state: the page applies these toggles itself, so a change only
  // needs remembering for the NEXT build — putting them in state would
  // reload the whole WebView on every checkbox, which is the map's known lag.
  const hiddenRegions = useRef<string[]>(services.settings.mapHiddenRegions);
  const showRail = useRef<boolean>(services.settings.mapShowRail);
  // The map remembers itself: every toggle writes through to Settings, so
  // the next visit — or the next launch — resumes where this one left off.
  function remember(patch: Partial<typeof services.settings>) {
    void services.applySettings({ ...services.settings, ...patch });
  }
  // A ref plus injection, not state: the list lands a beat after the page
  // builds, and as a useMemo dep it reloaded the whole map on every open.
  const visits = useRef<ScoutVisit[]>([]);
  useEffect(() => {
    void services.scoutVisitList().then((list) => {
      visits.current = list;
      const data = JSON.stringify(list);
      webRef.current?.injectJavaScript(
        `window.setVisits ? window.setVisits(${data})`
        + ` : (window.__pendingVisits = ${data}); true;`);
    });
  }, [services]);

  // What this map visit was actually given — synced with the device logs,
  // because "the rail is gone" on a phone in a hand is undiagnosable
  // without knowing which of five persisted toggles withheld the layer.
  useEffect(() => {
    log.info("map", "opened", {
      showScout, showTrees, hasScoutLayer: !!scoutLayer,
      hasTreeLayer: !!treeLayer,
      targets: scoutLayer?.targets.length ?? 0,
      rail: scoutLayer?.rail.length ?? 0,
      predators: scoutLayer?.predators.length ?? 0,
      regions: scoutLayer?.regions.length ?? 0,
      hiddenSpecies, hiddenRegions: hiddenRegions.current,
      showRail: showRail.current,
    });
    // Once per map open, whatever the toggles do afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * The compass. The magnetometer streams into the page's heading beam via
   * injected JS rather than rebuilding the HTML — a reload per degree would
   * redraw fifty thousand markers. Throttled to whole-degree changes; the
   * page ignores headings until it has a fix to anchor the beam to.
   */
  const webRef = useRef<WebView>(null);

  /** Back closes a zoomed photo before it leaves the map. */
  const photoOpen = useRef(false);
  useEffect(() => {
    setBackInterceptor(() => {
      if (!photoOpen.current) return false;
      photoOpen.current = false;
      webRef.current?.injectJavaScript("window.closePhoto && window.closePhoto(); true;");
      return true;
    });
    return () => setBackInterceptor(undefined);
  }, []);

  /**
   * Live position. The first fix plants the you-dot with one rebuild
   * (`prev ?? fix` keeps the state object stable afterwards); every later
   * fix glides the dot, halo and beam through injected JS, which is why the
   * map no longer needs closing and reopening to catch up with a walk.
   */
  useEffect(() => {
    let stop: (() => void) | undefined;
    let live = true;
    void services.location.watchPosition?.((fix) => {
      setHere((prev) => prev ?? fix);
      webRef.current?.injectJavaScript(
        `window.setPosition && window.setPosition(${fix.latitude}, `
        + `${fix.longitude}, ${fix.accuracyMeters ?? "null"}); true;`);
    }).then((unsubscribe) => {
      if (live) stop = unsubscribe;
      else unsubscribe();
    });
    return () => {
      live = false;
      stop?.();
    };
  }, [services]);

  useEffect(() => {
    let stop: (() => void) | undefined;
    let live = true;
    let last = -999;
    void services.location.watchHeading?.((degrees) => {
      const rounded = Math.round(degrees);
      if (rounded === last) return;
      last = rounded;
      webRef.current?.injectJavaScript(
        `window.setHeading && window.setHeading(${rounded}); true;`);
    }).then((unsubscribe) => {
      if (live) stop = unsubscribe;
      else unsubscribe();
    });
    return () => {
      live = false;
      stop?.();
    };
  }, [services]);
  const html = useMemo(
    () => buildMapHtml(placed, focusUuid, here,
      showTrees && treeLayer ? treeLayer.stands : undefined,
      showScout && scoutLayer ? scoutLayer : undefined,
      showTrees || showScout ? visits.current : undefined,
      familyHalos ? "family" : "keep",
      hiddenSpecies,
      hiddenRegions.current,
      showRail.current),
    // `here`, `hiddenSpecies` and `visits` are deliberately NOT deps: each
    // rebuild reloads the whole WebView — Leaflet, a megabyte of scout
    // layer, three thousand markers — which is the map's lag. The page
    // applies all of them itself (setPosition, the checklist, setVisits/
    // addVisit); the values here only seed the NEXT legitimate rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [placed, focusUuid, showTrees, treeLayer, showScout, scoutLayer,
     familyHalos],
  );
  const unplaced = shown.length - placed.length;
  const kept = useMemo(() => captures.filter((c) => c.keep).length, [captures]);
  // Counted against everything, not against what is on screen: "3 of 47" is the
  // honest split, and the map is exactly where a count over seeded clips with
  // fabricated coordinates looks like a statement about where crows are.
  const narrowed = describeView(filters, shown.length, captures.length);

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <View style={styles.headerRow}>
          {/* Equal-flex wings: the title centers on the row, not in whatever
              space the unequal back-link and toggles leave over. */}
          <View style={styles.wing}>
            <Pressable onPress={onBack} style={({ pressed }) => [pressed && styles.pressed]}>
              <Text style={styles.back}>‹ Captures</Text>
            </Pressable>
          </View>
          <Text style={[styles.title, brandFont]}>CawScout</Text>
          <View style={[styles.wing, styles.toggles]}>
            <Pressable
              onPress={() => setFamilyHalos((v) => {
                remember({ mapFamilyHalos: !v });
                return !v;
              })}
              style={({ pressed }) => [pressed && styles.pressed]}
              accessibilityRole="switch"
              accessibilityState={{ checked: familyHalos }}
              accessibilityLabel="Family halos"
            >
              <Text style={[styles.trees, familyHalos && styles.treesOn]}>👪</Text>
            </Pressable>
            {treeLayer ? (
              <Pressable
                onPress={() => setShowTrees((v) => {
              remember({ mapShowTrees: !v });
              return !v;
            })}
                style={({ pressed }) => [pressed && styles.pressed]}
                accessibilityRole="switch"
                accessibilityState={{ checked: showTrees }}
              >
                <Text style={[styles.trees, showTrees && styles.treesOn]}>🌲</Text>
              </Pressable>
            ) : null}
            {scoutLayer ? (
              <Pressable
                onPress={() => setShowScout((v) => {
              remember({ mapShowScout: !v });
              return !v;
            })}
                style={({ pressed }) => [pressed && styles.pressed]}
                accessibilityRole="switch"
                accessibilityState={{ checked: showScout }}
                accessibilityLabel="CawScout layer"
              >
                <Text style={[styles.trees, showScout && styles.treesOn]}>🎯</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
        <Text style={styles.count}>
          {/* Said plainly. An empty map with no explanation is how a privacy
              setting reads as lost data — which has already happened here once,
              with a filter. */}
          {mayShowCoords(precision, censor)
            ? `${placed.length} on map`
            : "Locations hidden — Settings › Location precision"}
          {mayShowCoords(precision, censor) && unplaced > 0 ? ` · ${unplaced} without GPS` : ""}
          {here ? " · you" : ""}
        </Text>
        {advice ? (
          <Pressable
            onPress={() => {
              if (forecastRef.current) onOpenSchedule(forecastRef.current);
            }}
            style={({ pressed }) => [pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel="Today's scouting schedule"
          >
            <Text style={[styles.window, advice.good && styles.windowGood]}>
              {advice.good ? "🐦 " : "💤 "}{advice.label} ›
            </Text>
          </Pressable>
        ) : null}
      </View>

      {/* The same bar as the capture list, driving the same state. The map is a
          rendering of that selection, not a separate view of the corpus — two
          answers to one question is how "I filtered to today" turns into "why
          does the map still show everything". */}
      <View style={styles.filters}>
        <CaptureFilterBar
          view={filters}
          keptCount={kept}
          waitingCount={
            captures.filter((c) => needsLabelling(c, labelCounts.get(c.uuid) ?? 0)).length
          }
          onChange={setFilters}
        />
        {narrowed ? (
          <Pressable
            onPress={() => setFilters(DEFAULT_VIEW)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.banner, pressed && styles.pressed]}
          >
            <Text style={styles.bannerText}>{narrowed} — tap to clear</Text>
          </Pressable>
        ) : null}
      </View>

      <WebView
        ref={webRef}
        style={styles.map}
        originWhitelist={["*"]}
        source={{ html }}
        javaScriptEnabled
        domStorageEnabled
        onMessage={(event) => {
          try {
            const message = JSON.parse(event.nativeEvent.data) as {
              type: string; uuid?: string;
              kind?: string; lat?: number; lon?: number; outcome?: string;
            };
            if (message.type === "photo-open") {
              photoOpen.current = true;
              return;
            }
            if (message.type === "photo-closed") {
              photoOpen.current = false;
              return;
            }
            if (message.type === "map-error") {
              log.error("map", `page error: ${(message as { message?: string }).message}`);
              return;
            }
            if (message.type === "locate") {
              // The page has no fix yet: fetch one and inject it — the dot
              // plants itself, and the button centers when pressed again.
              void services.location.current().then((fix) => {
                if (!fix) return;
                setHere(fix);
                webRef.current?.injectJavaScript(
                  `window.setPosition && window.setPosition(${fix.latitude}, `
                  + `${fix.longitude}, ${fix.accuracyMeters ?? "null"}); true;`);
              });
              return;
            }
            if (message.type === "street-view") {
              const m = message as { lat?: number; lon?: number };
              if (typeof m.lat === "number" && typeof m.lon === "number") {
                void Linking.openURL(
                  "https://www.google.com/maps/@?api=1&map_action=pano"
                  + `&viewpoint=${m.lat},${m.lon}`,
                ).catch(() => log.error("map", "could not open street view"));
              }
              return;
            }
            if (message.type === "directions") {
              const m = message as { lat?: number; lon?: number };
              if (typeof m.lat === "number" && typeof m.lon === "number") {
                // Destination only: Google Maps starts from the phone's own
                // location and lets the mode (walk, drive, TRAX) be chosen.
                void Linking.openURL(
                  "https://www.google.com/maps/dir/?api=1"
                  + `&destination=${m.lat},${m.lon}`,
                ).catch(() => log.error("map", "could not open directions"));
              }
              return;
            }
            if (message.type === "scout-area") {
              const m = message as { lat?: number; lon?: number; radius?: number };
              if (typeof m.lat === "number" && typeof m.lon === "number"
                  && typeof m.radius === "number") {
                void services.scoutSpots(m.lat, m.lon, m.radius)
                  .then(({ spots, note }) => {
                    const script = spots.length
                      ? `window.showSpots && window.showSpots(${JSON.stringify(spots)})`
                      : `window.scoutNote && window.scoutNote(${
                          JSON.stringify(note ?? "nothing scored in this circle")})`;
                    webRef.current?.injectJavaScript(`${script}; true;`);
                  });
              }
              return;
            }
            if (message.type === "region-filter") {
              const m = message as { slug?: string; on?: boolean };
              if (typeof m.slug === "string") {
                hiddenRegions.current = m.on
                  ? hiddenRegions.current.filter((s) => s !== m.slug)
                  : [...new Set([...hiddenRegions.current, m.slug])];
                remember({ mapHiddenRegions: hiddenRegions.current });
              }
              return;
            }
            if (message.type === "rail-toggle") {
              const m = message as { on?: boolean };
              if (typeof m.on === "boolean") {
                showRail.current = m.on;
                remember({ mapShowRail: m.on });
              }
              return;
            }
            if (message.type === "species-filter") {
              const m = message as { name?: string; on?: boolean };
              if (typeof m.name === "string") {
                const hidden = m.on
                  ? hiddenSpecies.filter((s) => s !== m.name)
                  : [...new Set([...hiddenSpecies, m.name])];
                setHiddenSpecies(hidden);
                remember({ mapHiddenSpecies: hidden });
              }
              return;
            }
            if (message.type === "scout-visit" && message.kind
                && typeof message.lat === "number"
                && typeof message.lon === "number"
                && (message.outcome === "crows" || message.outcome === "nothing")) {
              const mark = {
                latitude: message.lat, longitude: message.lon,
                outcome: message.outcome,
                visitedAt: new Date().toISOString(),
              };
              visits.current = [...visits.current, mark as ScoutVisit];
              void services
                .addScoutVisit(message.kind as VisitKind, message.lat,
                               message.lon, message.outcome)
                .then(() => {
                  // Injected, not rebuilt: the page adds the mark itself.
                  // The next map open refetches the authoritative list.
                  webRef.current?.injectJavaScript(
                    `window.addVisit && window.addVisit(${JSON.stringify(mark)}); true;`);
                });
              return;
            }
            if (message.type !== "open" || !message.uuid) return;
            const found = captures.find((capture) => capture.uuid === message.uuid);
            if (found) onOpenCapture(found);
          } catch {
            // A malformed message from the page is not worth crashing the screen over.
          }
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "column",
    alignItems: "flex-start",
    gap: 2,
    paddingHorizontal: spacing.lg,
    paddingTop: 56,
    paddingBottom: spacing.sm,
  },
  back: { color: colors.accent, fontSize: 16 },
  title: { color: colors.text, fontSize: 16, fontWeight: "700" },
  headerRow: { flexDirection: "row", alignItems: "center", gap: 10,
    alignSelf: "stretch" },
  wing: { flex: 1, flexDirection: "row" },
  toggles: { alignItems: "center", justifyContent: "flex-end", gap: 4 },
  trees: { fontSize: 18, opacity: 0.35, paddingHorizontal: 6 },
  treesOn: { opacity: 1 },
  count: { color: colors.textMuted, fontSize: 12 },
  window: { color: colors.textFaint, fontSize: 12 },
  windowGood: { color: colors.good },
  filters: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, gap: spacing.xs },
  banner: {
    backgroundColor: colors.surfaceDeep,
    borderWidth: 1,
    borderColor: colors.warn,
    borderRadius: radius.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
  },
  bannerText: { color: colors.warn, fontSize: 11, textAlign: "center" },
  pressed: { opacity: 0.6 },
  map: { flex: 1, backgroundColor: colors.background },
});
