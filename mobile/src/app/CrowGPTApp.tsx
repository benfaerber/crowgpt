import { useCallback, useEffect, useState } from "react";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, BackHandler, StyleSheet, Text, View } from "react-native";

import { newClientUuid } from "../domain/ids";
import { deviceRandomBytes } from "../platform/random";
import { CaptureDetailScreen } from "../ui/CaptureDetailScreen";
import { CaptureListScreen } from "../ui/CaptureListScreen";
import { RecorderProvider } from "./RecorderContext";
import { LabelingScreen } from "../ui/LabelingScreen";
import { DiagnosticsScreen } from "../ui/DiagnosticsScreen";
import { DiagnosticsHubScreen } from "../ui/DiagnosticsHubScreen";
import { CueDiagnosticsScreen } from "../ui/CueDiagnosticsScreen";
import { HeadsetDiagnosticsScreen } from "../ui/HeadsetDiagnosticsScreen";
import { GuideScreen } from "../ui/GuideScreen";
import { LogScreen } from "../ui/LogScreen";
import { FamilyScreen } from "../ui/FamilyScreen";
import { MapScreen } from "../ui/MapScreen";
import { ScoutScheduleScreen } from "../ui/ScoutScheduleScreen";
import { VideoCaptureScreen } from "../ui/VideoCaptureScreen";
import { PermissionsScreen } from "../ui/PermissionsScreen";
import { SettingsScreen } from "../ui/SettingsScreen";
import { DEFAULT_VIEW, type CaptureView } from "../domain/captureFilters";
import { ErrorBoundary } from "../ui/components/ErrorBoundary";
import { colors } from "../ui/theme";
import { AppServices, type Settings } from "./AppServices";
import { defaultSettings } from "./adapters";
import { installGlobalLogging, log } from "./Log";
import { RouteStack, type Route } from "./navigation";
import { runBackInterceptor } from "./backInterceptor";
import { scrollMemory } from "../ui/useRememberedScroll";

// At module scope, so it is running before the first render rather than inside
// an effect that a startup crash would never reach. Here rather than in
// index.ts because that file is Expo's — it exists to call
// registerRootComponent and should keep doing only that — and this is the next
// thing loaded, which is early enough to catch everything the app does.
log.useRandomBytes(deviceRandomBytes);
installGlobalLogging();
log.info("app", "launched");

/**
 * The app root.
 *
 * Screen switching is a plain route stack rather than a navigation library:
 * a dozen screens and push/pop semantics do not justify pulling in
 * react-navigation and its native dependencies. See RouteStack for why a
 * stack and not a parent table.
 */
export function CrowGPTApp() {
  const [services, setServices] = useState<AppServices | null>(null);
  const [startupError, setStartupError] = useState<string | undefined>();
  const [stack, setStack] = useState<RouteStack>(RouteStack.root);
  const route = stack.current;
  // Opening a screen fresh forgets its old scroll position; popping back to
  // one restores it — Settings -> App Log -> back lands beside the App Log
  // row, not at the top.
  const push = useCallback((next: Route) => {
    scrollMemory.forget(next.name);
    setStack((s) => s.push(next));
  }, []);
  const back = useCallback(() => setStack((s) => s.pop()), []);

  // The label set is the operator's to define, so ask rather than assume — and
  // only once per launch: it changes on a config push, not on a screen change.
  useEffect(() => {
    if (services) void services.refreshConfig();
    // The trees layer rides the same launch-time window, for the same
    // reason: it changes when somebody republishes it, not per screen.
    if (services) void services.refreshTrees();
    if (services) void services.refreshScout();
  }, [services]);

  /**
   * Bring the analysis down at launch, while there is probably still a network.
   *
   * The end of a sync is the obvious place for this and it happens there too,
   * but it is not enough on its own: the Sync button is disabled when nothing
   * is waiting, which is precisely the state of a phone whose owner is about to
   * walk out of the door. Doing it at launch means the detections are on the
   * phone without anyone having to perform a ritual before leaving.
   *
   * Cheap and quiet — a few kilobytes of JSON per capture over a LAN, and it
   * gives up after three failures in a row rather than grinding through three
   * hundred doomed requests when there is no server at all.
   */
  // Once, ever: captures recorded before regions existed already carry the
  // answer in their own fix, and reading it is what stops every old row saying
  // "no location". Silent — there is nothing here for anyone to decide.
  useEffect(() => {
    if (services) void services.backfillRegionsOnce();
  }, [services]);

  // Push whatever the log is holding, as soon as there is somewhere to push it.
  //
  // It only went up at the end of a sync, which is exactly the trip that fails
  // when something has gone wrong in the field: a phone that spent an afternoon
  // out of range came home still holding the only account of it, and it stayed
  // there until somebody thought to sync. Launching is a better moment — it is
  // the first thing that happens after getting back.
  useEffect(() => {
    if (services) void services.syncLogs();
    if (services) void services.syncScoutVisits();
  }, [services]);

  useEffect(() => {
    if (!services) return;
    void services
      .prefetchAnalysis()
      .then((warm) =>
        // Level by outcome, not by "it returned". A run that gave up because
        // there was no server is a failure written as a success if it is filed
        // under info, and the whole point of the log is that failures are the
        // entries worth having.
        warm.offline || warm.failed > 0
          ? log.warn("analysis", "cache warm incomplete at launch", warm)
          : log.info("analysis", "cache warmed at launch", warm),
      )
      .catch((failure) => log.warn("analysis", "launch cache warm failed", failure));
  }, [services]);

  useEffect(() => {
    let live = true;
    AppServices.create(defaultSettings)
      .then((built) => live && setServices(built))
      .catch((error) => {
        log.error("app", "startup failed", error);
        if (live) setStartupError(error instanceof Error ? error.message : String(error));
      });
    return () => {
      live = false;
    };
  }, []);

  // Descriptions are written on the detail screen but owned by the store, so the
  // action lives here and the screen just calls it.
  const describe = useCallback(
    async (uuid: string, body: string) => {
      const repository = services!.repository;
      const existing = await repository.get(uuid);
      const now = new Date().toISOString();
      return repository.update(uuid, {
        description: body,
        descriptionUuid: existing?.descriptionUuid ?? newClientUuid(deviceRandomBytes),
        descriptionUpdatedAt: now,
        ...(existing?.syncState === "synced" ? { syncState: "local" as const } : {}),
      });
    },
    [services],
  );

  /**
   * Android's back gesture and button.
   *
   * Without this every screen is a dead end: back exits the app outright rather
   * than returning to the list, which on the map or a capture detail feels like
   * a crash. Back pops the route stack, so it retraces the trip that got here
   * — a capture opened from the map returns to the map, not the list.
   */
  useEffect(() => {
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      // A screen may claim the press first — the map does, to close a
      // zoomed photo instead of leaving the map.
      if (runBackInterceptor()) return true;
      if (stack.atRoot) return false; // let Android leave the app
      back();
      return true;
    });
    return () => subscription.remove();
  }, [stack, back]);

  /**
   * Which captures the list and the map are both showing.
   *
   * One state above both, because they are the same selection rendered two
   * ways — filtering to today on the list and finding the map still showing
   * everything is two answers to one question.
   *
   * Session-scoped rather than persisted. A filter that survives a restart is
   * how "today" quietly hides tomorrow's work, and this app has already had one
   * scare where a narrowed list read as data loss.
   */
  const [captureView, setCaptureView] = useState<CaptureView>(DEFAULT_VIEW);

  /**
   * Settings live on the services object, which React does not watch, so a
   * change had to be paired with something that forces a render.
   *
   * Without it the pocket-mic switch was controlled by a value that did not
   * update when it was tapped: React Native's Switch animates immediately, sees
   * the prop it was given unchanged on the next render, and snaps back — firing
   * onValueChange a second time with the opposite answer. The log caught it
   * doing exactly that, one second apart.
   */
  // Deliberately not a key on the screen below: changing a key remounts, which
  // would tear down the recorder and restart the microphone session every time
  // a switch moved. Re-rendering is all that is needed — the children read the
  // mutated object and see the new value.
  const [, setSettingsRevision] = useState(0);
  const handleSettings = useCallback(
    (settings: Settings) => {
      services?.applySettings(settings);
      setSettingsRevision((n) => n + 1);
    },
    [services],
  );

  /**
   * A capture was written. Bumped here rather than calling the list's refresh,
   * because the recorder now outlives that screen: a headset press from
   * Settings records and stops without the list being mounted to be told.
   *
   * A counter rather than a callback into the list, so the list can reload when
   * it next sees a number it has not seen — including on the trip back from
   * Settings, where the capture that landed while it was unmounted is exactly
   * the one missing from it.
   */
  const [recordedTick, setRecordedTick] = useState(0);
  const handleRecorded = useCallback(() => setRecordedTick((n) => n + 1), []);

  const handleDelete = useCallback(
    async (uuid: string) => {
      // Through deleteCaptures rather than repository.remove: the row was the
      // only thing being deleted, so every capture ever deleted left its WAV
      // behind on the phone.
      await services?.deleteCaptures([uuid]);
      back();
    },
    [services, back],
  );

  const handleUnmerge = useCallback(
    async (uuid: string) => {
      // Through services.unmerge for the same reason delete goes through
      // deleteCaptures: the domain half forgets the row, and only the service
      // knows about the assembled WAV the row was standing in front of.
      await services?.unmerge(uuid);
      back();
    },
    [services, back],
  );

  if (!services) {
    return (
      <View style={styles.startup}>
        <StatusBar style="light" />
        {startupError ? (
          <>
            <Text style={styles.startupTitle}>Couldn&apos;t open the local store</Text>
            <Text style={styles.startupBody}>{startupError}</Text>
          </>
        ) : (
          <ActivityIndicator size="large" color={colors.accent} />
        )}
      </View>
    );
  }

  return (
    // Around the screens, inside the app: a render failure below this loses the
    // screen and keeps the app, rather than dropping the recordist onto a black
    // rectangle with no way back.
    <ErrorBoundary>
      {/* Outside the routes, so the earbud button survives leaving the capture
          screen. See RecorderProvider — a press from Settings used to be
          swallowed by the native session and then land on nothing. */}
      <RecorderProvider services={services} onRecorded={handleRecorded}>
      <View style={{ flex: 1, backgroundColor: colors.background }}>
        <StatusBar style="light" />
        {route.name === "list" && (
          <CaptureListScreen
            services={services}
            onSettingsChange={handleSettings}
            recordedTick={recordedTick}
            view={captureView}
            onViewChange={setCaptureView}
            onOpenCapture={(capture) => push({ name: "detail", capture })}
            onOpenGuide={() => push({ name: "guide" })}
            onOpenSettings={() => push({ name: "settings" })}
            onOpenMap={() => push({ name: "map" })}
            onRecordVideo={() => push({ name: "video" })}
          />
        )}
        {route.name === "detail" && (
          <CaptureDetailScreen
            services={services}
            capture={route.capture}
            onBack={back}
            onDelete={handleDelete}
            onUnmerge={handleUnmerge}
            onViewOnMap={(target) => push({ name: "map", focusUuid: target.uuid })}
            onDescribe={describe}
            onCreateFamily={() => push({ name: "families" })}
            onLabel={() => push({ name: "labeling", capture: route.capture })}
          />
        )}
        {route.name === "labeling" && (
          <LabelingScreen
            services={services}
            capture={route.capture}
            onBack={back}
          />
        )}
        {route.name === "settings" && (
          <SettingsScreen
            services={services}
            onBack={back}
            onChange={handleSettings}
            onOpenDiagnostics={() => push({ name: "diagnostics" })}
            onOpenLogs={() => push({ name: "logs" })}
            onOpenPermissions={() => push({ name: "permissions" })}
            onOpenFamilies={() => push({ name: "families" })}
          />
        )}
        {route.name === "families" && (
          <FamilyScreen services={services} onBack={back} onCreated={back} />
        )}
        {route.name === "video" && (
          <VideoCaptureScreen services={services} onBack={back} onCaptured={back} />
        )}
        {route.name === "map" && (
          <MapScreen
            services={services}
            view={captureView}
            onViewChange={setCaptureView}
            focusUuid={route.focusUuid}
            onBack={back}
            onOpenCapture={(capture) => push({ name: "detail", capture })}
            onOpenSchedule={(forecast) =>
              push({ name: "scout-schedule", forecast })}
          />
        )}
        {route.name === "scout-schedule" && (
          <ScoutScheduleScreen forecast={route.forecast} onBack={back} />
        )}
        {route.name === "permissions" && (
          <PermissionsScreen permissions={services.permissions} onBack={back} />
        )}
        {route.name === "diagnostics" && (
          <DiagnosticsHubScreen
            onBack={back}
            onOpenMicSources={() => push({ name: "mic-sources" })}
            onOpenHeadset={() => push({ name: "headset" })}
            onOpenCues={() => push({ name: "cues" })}
            onOpenLogs={() => push({ name: "logs" })}
          />
        )}
        {route.name === "mic-sources" && <DiagnosticsScreen onBack={back} />}
        {route.name === "cues" && <CueDiagnosticsScreen onBack={back} />}
        {route.name === "headset" && (
          <HeadsetDiagnosticsScreen services={services} onBack={back} />
        )}
        {route.name === "guide" && <GuideScreen services={services} onBack={back} />}
        {route.name === "logs" && <LogScreen services={services} onBack={back} />}
      </View>
      </RecorderProvider>
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  startup: {
    flex: 1,
    backgroundColor: colors.background,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    padding: 24,
  },
  startupTitle: { color: colors.bad, fontSize: 16, fontWeight: "700" },
  startupBody: { color: colors.textMuted, fontSize: 13, textAlign: "center" },
});
