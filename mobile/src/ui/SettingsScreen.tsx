import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import type { AppServices, Settings } from "../app/AppServices";
import { describeRole } from "../domain/identity";
import { KeyboardAwareScroll } from "./components/KeyboardAwareScroll";
import { LocationPrecisionPicker } from "./components/LocationPrecisionPicker";
import { MicPicker, useAudioInputs } from "./components/MicPicker";
import type { KnownMic } from "../domain/micPriority";
import { micState } from "../domain/micState";
import { currentBuild, formatCommitTime, formatVersion } from "../app/buildInfo";
import { normalizeHeartbeatSeconds } from "../domain/heartbeat";
import { clampIdle, IDLE_BOUNDS } from "../domain/idle";
import { PRE_ROLL_SEC } from "../recording/Recorder";
import { colors, pageEnd, radius, spacing } from "./theme";
import { useRememberedScroll } from "./useRememberedScroll";

export function SettingsScreen({
  services,
  onBack,
  onChange,
  onOpenDiagnostics,
  onOpenLogs,
  onOpenPermissions,
  onOpenFamilies,
}: {
  services: AppServices;
  onBack: () => void;
  onChange: (settings: Settings) => void;
  onOpenDiagnostics: () => void;
  onOpenLogs: () => void;
  onOpenPermissions: () => void;
  onOpenFamilies: () => void;
}) {
  const scroll = useRememberedScroll("settings");
  const [draft, setDraft] = useState<Settings>(services.settings);
  const [message, setMessage] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [enrollments, setEnrollments] = useState(0);
  const inputs = useAudioInputs(
    () => services.recorder.listInputs?.() ?? [],
    () => services.refreshMicrophones(),
  );
  // Folding what is attached into the remembered list happens here rather than
  // at launch: this is the only screen that reads it, and a phone being used to
  // record should not write to storage for a list nobody is looking at.
  const [mics, setMics] = useState<KnownMic[]>(() => services.rememberAttachedMics());
  // Again once the OS has answered: the first pass runs during render and can
  // only see the snapshot from before this screen opened, which on a phone that
  // has just had a microphone plugged in is the wrong list.
  useEffect(() => {
    if (inputs.length > 0) setMics(services.rememberAttachedMics());
  }, [inputs, services]);

  // Text fields edit the draft only. Committing on every keystroke would apply
  // a half-typed address as if it were a real server change, and changing server
  // resets every capture's sync state.
  const edit = (patch: Partial<Settings>) => setDraft((current) => ({ ...current, ...patch }));

  /** Called on blur, and for controls where every change is already deliberate. */
  const commit = (patch: Partial<Settings> = {}) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    onChange(next);
  };

  // Their own string state because the settings are numbers: a draft typed as
  // Settings cannot hold "1" on the way to "15" without applying it.
  const [listeningBeatText, setListeningBeatText] = useState(
    String(services.settings.heartbeatListeningSeconds),
  );
  const [recordingBeatText, setRecordingBeatText] = useState(
    String(services.settings.heartbeatRecordingSeconds),
  );

  const commitListeningBeat = () => {
    const heartbeatListeningSeconds = normalizeHeartbeatSeconds(
      listeningBeatText,
      draft.heartbeatListeningSeconds,
    );
    // The box shows what was applied, not what was typed — "2" left standing
    // over a clamped 5 would be this screen lying about the interval.
    setListeningBeatText(String(heartbeatListeningSeconds));
    commit({ heartbeatListeningSeconds });
  };

  const commitRecordingBeat = () => {
    const heartbeatRecordingSeconds = normalizeHeartbeatSeconds(
      recordingBeatText,
      draft.heartbeatRecordingSeconds,
    );
    setRecordingBeatText(String(heartbeatRecordingSeconds));
    commit({ heartbeatRecordingSeconds });
  };

  /**
   * The idle numbers, edited as text for the same reason as the beats: a
   * draft typed as Settings cannot hold "1" on the way to "15" without
   * applying it. One state object rather than six, because the six rows are
   * one shape repeated.
   */
  const [idleText, setIdleText] = useState({
    idleArmMinutes: String(services.settings.idleArmMinutes),
    idleHoldSeconds: String(services.settings.idleHoldSeconds),
    idleMaxCaptureMinutes: String(services.settings.idleMaxCaptureMinutes),
    idleMaxCaptures: String(services.settings.idleMaxCaptures),
    idleTriggerDb: String(services.settings.idleTriggerDb),
    idleMinDb: String(services.settings.idleMinDb),
  });
  type IdleNumberKey = keyof typeof idleText;

  /** A render function, not a component: a component defined inside render
   *  would remount its TextInput on every keystroke and drop the focus. */
  const idleRow = (
    label: string,
    unit: string,
    key: IdleNumberKey,
    bounds: { min: number; max: number },
  ) => (
    <View style={[styles.switchRow, styles.nested]}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={[styles.input, styles.interval]}
        value={idleText[key]}
        onChangeText={(value) => setIdleText((s) => ({ ...s, [key]: value }))}
        keyboardType={bounds.min < 0 ? "default" : "number-pad"}
        onEndEditing={() => {
          const value = clampIdle(idleText[key], bounds, draft[key]);
          // The box shows what was applied, not what was typed — same rule
          // as the heartbeat intervals.
          setIdleText((s) => ({ ...s, [key]: String(value) }));
          commit({ [key]: value } as Partial<Settings>);
        }}
        placeholderTextColor={colors.textFaint}
      />
      <Text style={styles.label}>{unit}</Text>
    </View>
  );

  const [restoring, setRestoring] = useState<string | undefined>();

  const restore = async () => {
    setBusy(true);
    setRestoring("Looking…");
    setMessage(undefined);
    try {
      const outcome = await services.restoreFromServer((done, total) =>
        setRestoring(`Restoring ${done} of ${total}…`),
      );
      const parts = [`${outcome.restored.length} restored`];
      if (outcome.skipped) parts.push(`${outcome.skipped} already here`);
      if (outcome.unavailable) parts.push(`${outcome.unavailable} with no audio`);
      if (outcome.failed.length) parts.push(`${outcome.failed.length} failed`);
      setMessage(parts.join(" · "));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setRestoring(undefined);
      setBusy(false);
    }
  };

  const [warming, setWarming] = useState<string | undefined>();

  const warmAnalysis = async () => {
    setBusy(true);
    setWarming("Looking…");
    setMessage(undefined);
    try {
      const outcome = await services.prefetchAnalysis((done, total) =>
        setWarming(`${done} of ${total}…`),
      );
      const parts = [`${outcome.stored} stored`];
      if (outcome.pending) parts.push(`${outcome.pending} not analyzed yet`);
      if (outcome.failed) parts.push(`${outcome.failed} failed`);
      setMessage(parts.join(" · "));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setWarming(undefined);
      setBusy(false);
    }
  };

  const check = async (action: "health" | "enroll") => {
    setBusy(true);
    setMessage(undefined);
    try {
      if (action === "health") {
        const health = await services.fieldServer.health();
        setMessage(`Server reachable — config v${health.config_version}`);
      } else {
        const identity = await services.enroll();
        setMessage(`Enrolled as ${identity.contributorName}.`);
        // The identity panel reads services.identity when it mounts, and before
        // enrolling there was nothing to show — remount it so it appears.
        setEnrollments((n) => n + 1);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={({ pressed }) => [pressed && styles.pressed]}>
          <Text style={styles.back}>‹ Captures</Text>
        </Pressable>
      </View>

      <KeyboardAwareScroll {...scroll} contentContainerStyle={styles.body}>
        <Text style={styles.title}>Settings</Text>

        <View style={styles.group}>
          <Text style={styles.label}>Field server</Text>
          <TextInput
            style={styles.input}
            value={draft.fieldServerUrl}
            onChangeText={(fieldServerUrl) => edit({ fieldServerUrl })}
            onEndEditing={() => commit()}
            onBlur={() => commit()}
            autoCapitalize="none"
            autoCorrect={false}
            placeholderTextColor={colors.textFaint}
          />
          <Text style={styles.hint}>
            The address `make field` prints. Saved when you tap away from the field;
            changing it forgets this device&apos;s enrollment and marks captures for
            re-upload, so it is only applied once you finish typing.
          </Text>
        </View>

        <View style={styles.group}>
          <Text style={styles.label}>Your name</Text>
          <TextInput
            style={styles.input}
            value={draft.contributorName}
            onChangeText={(contributorName) => edit({ contributorName })}
            onEndEditing={() => commit()}
            onBlur={() => commit()}
            placeholder="Shown against your captures"
            placeholderTextColor={colors.textFaint}
          />
          <Text style={styles.hint}>
            Who collected these recordings. Everything you have already sent is
            renamed too — it is one person, not a label on each capture.
          </Text>
        </View>

        <View style={styles.group}>
          <Text style={styles.label}>This device</Text>
          <TextInput
            style={styles.input}
            value={draft.deviceLabel}
            onChangeText={(deviceLabel) => edit({ deviceLabel })}
            onEndEditing={() => commit()}
            onBlur={() => commit()}
            placeholder="e.g. Pixel 10"
            placeholderTextColor={colors.textFaint}
          />
          <Text style={styles.hint}>
            How this phone is named in the fleet. Both your phones can hold the
            same captures — this is how you tell which one recorded what.
          </Text>
        </View>

        {!services.isEnrolled ? (
          <View style={styles.group}>
            <Text style={styles.label}>Claim code (optional)</Text>
            <TextInput
              style={styles.input}
              value={draft.claimCode}
              onChangeText={(claimCode) => edit({ claimCode })}
              onEndEditing={() => commit()}
              onBlur={() => commit()}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="Paste to add this phone to an existing account"
              placeholderTextColor={colors.textFaint}
            />
            <Text style={styles.hint}>
              From your other phone&apos;s Settings. Leave empty to start a new
              account — without it this handset becomes a separate contributor and
              won&apos;t see your existing captures or families.
            </Text>
          </View>
        ) : null}

        {/* Only until it has been used. It is the shared secret that joins a
            phone to the fleet, it is needed exactly once, and leaving it in an
            always-visible box is how it ends up read over somebody's shoulder
            or copied to a phone that was never meant to have it. */}
        {services.isEnrolled ? null : (
          <View style={styles.group}>
            <Text style={styles.label}>Enrollment token</Text>
            <TextInput
              style={styles.input}
              value={draft.enrollToken}
              onChangeText={(enrollToken) => edit({ enrollToken })}
              onEndEditing={() => commit()}
              onBlur={() => commit()}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <Text style={styles.hint}>
              Joins this phone to the fleet, once. It disappears from here after
              that — ask for a new one if this phone ever has to enrol again.
            </Text>
          </View>
        )}

        <MicPicker
          mics={mics}
          attached={inputs}
          state={micState({
            priority: mics,
            attached: inputs,
            session: services.recorder.activeInput?.() ?? null,
          })}
          onChange={(micPriority) => {
            setMics(micPriority);
            commit({ micPriority });
          }}
        />

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>Rolling buffer</Text>
            <Text style={styles.hint}>
              Keep the microphone open so Record reaches back {PRE_ROLL_SEC} seconds. By
              the time a call is heard and the button found, the call is over. Only while
              this app is on screen, unless you also turn on the setting below.
            </Text>
          </View>
          <Switch
            value={draft.preRoll}
            onValueChange={(preRoll) =>
              // Clearing the nested flags on the way down: leaving them set
              // means switching the buffer back on months later silently
              // resumes pocket listening — or an armed idle mode — which is
              // not what the tap asked for.
              commit(preRoll
                ? { preRoll }
                : { preRoll, backgroundListening: false, idleMode: false })
            }
            trackColor={{ true: colors.accent, false: colors.border }}
          />
        </View>

        {/* Nested under the buffer, and only offered once it is on: there is
            nothing to keep listening for otherwise, and a phone that quietly
            holds its microphone because a different switch was flipped is the
            kind of thing that ends up in an article. */}
        {draft.preRoll ? (
          <View style={[styles.switchRow, styles.nested]}>
            <View style={styles.switchText}>
              <Text style={styles.label}>…even with the screen off</Text>
              <Text style={styles.hint}>
                Keeps listening from your pocket, which is when a call is most likely
                to be missed. Android requires a permanent notification while the
                microphone is open, and it will cost battery all day.
              </Text>
            </View>
            <Switch
              value={draft.backgroundListening}
              onValueChange={(backgroundListening) => {
                commit({ backgroundListening });
                // Android will not show the ongoing notification without this,
                // and a microphone held from a pocket with nothing on screen to
                // say so is the situation the notification exists to prevent.
                if (backgroundListening) {
                  void services.permissions.request("notifications");
                }
              }}
              trackColor={{ true: colors.warn, false: colors.border }}
            />
          </View>
        ) : null}

        {/* The buffer's third member: pocket listening keeps the ring alive
            unattended, idle mode makes it press Record too. Nested under the
            same switch because it is the same microphone being held — and
            turning it on turns pocket listening on with it, since an armed
            hour is exactly the screen-off case and a mode that only worked
            while somebody watched the screen would be idle in name only. */}
        {draft.preRoll ? (
          <View style={[styles.switchRow, styles.nested]}>
            <View style={styles.switchText}>
              <Text style={styles.label}>…and record on its own (idle mode)</Text>
              <Text style={styles.hint}>
                While armed, a crow call starts a capture by itself, reaching
                back through the buffer — mic on the fire escape, phone on the
                charger. Each bout becomes its own capture, marked AUTO with
                role and distance left blank: nobody was there to answer. This
                switch only shows the controls; arming is a button on the
                capture screen, per session.
              </Text>
            </View>
            <Switch
              value={draft.idleMode}
              onValueChange={(idleMode) => {
                // Pocket listening comes on with it rather than being assumed:
                // the armed hour runs with the screen off, and the switch that
                // says so should be visibly on.
                commit(idleMode ? { idleMode, backgroundListening: true } : { idleMode });
                if (idleMode) {
                  void services.permissions.request("notifications");
                }
              }}
              trackColor={{ true: colors.warn, false: colors.border }}
            />
          </View>
        ) : null}

        {draft.preRoll && draft.idleMode ? (
          <>
            {idleRow("Armed for", "min", "idleArmMinutes",
              IDLE_BOUNDS.armMinutes)}
            {idleRow("Stop after", "s quiet", "idleHoldSeconds",
              IDLE_BOUNDS.holdSeconds)}
            {idleRow("Cap captures at", "min", "idleMaxCaptureMinutes",
              IDLE_BOUNDS.maxCaptureMinutes)}
            {idleRow("Give up after", "captures", "idleMaxCaptures",
              IDLE_BOUNDS.maxCaptures)}
            {idleRow("Trigger at floor +", "dB", "idleTriggerDb",
              IDLE_BOUNDS.triggerDb)}
            {idleRow("But never under", "dBFS", "idleMinDb",
              IDLE_BOUNDS.minDb)}
            <Text style={[styles.hint, styles.nested]}>
              The trigger listens only in the 800–4000 Hz crow band and measures
              the evening&apos;s own noise floor; 12 dB over it is the level a
              real burst clears and traffic does not. Leave these alone unless a
              session over- or under-triggered.
            </Text>
          </>
        ) : null}

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>Heartbeat while listening</Text>
            <Text style={styles.hint}>
              A soft tick in the earbuds for as long as the mic is open — so a
              buffer that has silently died is knowable with the phone still in
              your pocket. Silence means stopped, which is the thing worth
              finding out before the crow calls. Tones rather than words:
              anything the phone says out loud lands in the recording. Music
              dips briefly around each one; with no earbuds it vibrates
              instead.
            </Text>
          </View>
          <Switch
            value={draft.heartbeatListening}
            onValueChange={(heartbeatListening) => commit({ heartbeatListening })}
            trackColor={{ true: colors.accent, false: colors.border }}
          />
        </View>

        {draft.heartbeatListening ? (
          <View style={[styles.switchRow, styles.nested]}>
            <Text style={styles.label}>Alert every</Text>
            <TextInput
              style={[styles.input, styles.interval]}
              value={listeningBeatText}
              onChangeText={setListeningBeatText}
              keyboardType="number-pad"
              onEndEditing={() => commitListeningBeat()}
              onBlur={() => commitListeningBeat()}
              placeholderTextColor={colors.textFaint}
            />
            <Text style={styles.label}>seconds</Text>
          </View>
        ) : null}

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>Heartbeat while recording</Text>
            <Text style={styles.hint}>
              A double beep for the length of a capture — reassurance that the
              recording you started is still running, on its own faster
              rhythm. Independent of the tick above: with this off, a capture
              is silent even while that one is on, because a tick saying
              &quot;listening&quot; mid-recording would be the phone claiming
              a state it is not in.
            </Text>
          </View>
          <Switch
            value={draft.heartbeatRecording}
            onValueChange={(heartbeatRecording) => commit({ heartbeatRecording })}
            trackColor={{ true: colors.accent, false: colors.border }}
          />
        </View>

        {draft.heartbeatRecording ? (
          <View style={[styles.switchRow, styles.nested]}>
            <Text style={styles.label}>Alert every</Text>
            <TextInput
              style={[styles.input, styles.interval]}
              value={recordingBeatText}
              onChangeText={setRecordingBeatText}
              keyboardType="number-pad"
              onEndEditing={() => commitRecordingBeat()}
              onBlur={() => commitRecordingBeat()}
              placeholderTextColor={colors.textFaint}
            />
            <Text style={styles.label}>seconds</Text>
          </View>
        ) : null}

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>Record from the earbud button</Text>
            <Text style={styles.hint}>
              A tap of the headset play/pause button starts a recording; another
              stops it. A beep in your ears confirms — high for started, lower
              for stopped, an error trill if nothing was recorded.
              {"\n\n"}
              While something else is playing, the button belongs to whatever is
              playing it. Pause your music first and the next tap records — this
              app takes the button back the moment the audio stops, and Android
              gives it to whoever made a sound most recently, which cannot be
              won from an app that has not stopped. Nothing here ever pauses
              what you are listening to.
              {"\n\n"}
              In a bag it needs the pocket mic above, or Android may take the
              button back with the screen off.
            </Text>
          </View>
          <Switch
            value={draft.headsetTrigger}
            onValueChange={(headsetTrigger) => commit({ headsetTrigger })}
            trackColor={{ true: colors.accent, false: colors.border }}
          />
        </View>

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>Record from a camera remote</Text>
            <Text style={styles.hint}>
              A Bluetooth shutter remote presses the volume key — that is the
              only thing it can send, because volume is every phone camera's
              shutter. With this on, a press starts a recording and another
              stops it, with the same beeps as the earbud button.
              {"\n\n"}
              Works while this app is on screen; with the screen off the press
              goes back to being a volume key. While on, the volume keys —
              the phone's own rocker included — record instead of changing the
              volume, but only inside this app.
            </Text>
          </View>
          <Switch
            value={draft.volumeShutter}
            onValueChange={(volumeShutter) => commit({ volumeShutter })}
            trackColor={{ true: colors.accent, false: colors.border }}
          />
        </View>

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>Lock the screen while recording</Text>
            <Text style={styles.hint}>
              Covers the screen for the length of a capture, so only a deliberate
              slide can end it. On by default, unlike everything else here: a
              recording that should have stopped and did not costs some disk, and
              one that stopped when it should not have is gone. Shorts, a pocket
              and a damp leg are enough — the screen reads that as a finger. The
              earbud button still works, because that is a press you meant.
            </Text>
          </View>
          <Switch
            value={draft.captureLock}
            onValueChange={(captureLock) => commit({ captureLock })}
            trackColor={{ true: colors.accent, false: colors.border }}
          />
        </View>

        {/* Above the playback settings, because it is the one on this screen
            that decides what other people can learn about you. */}
        <LocationPrecisionPicker
          precision={draft.locationPrecision}
          censor={draft.censorCoords}
          fuzzMiles={draft.fuzzMiles}
          region={draft.homeRegion}
          onChange={(next) => commit(next)}
        />

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>Turn captures up for playback</Text>
            <Text style={styles.hint}>
              A crow ten metres up peaks around -30 dBFS, so reviewing one means
              holding the phone to your ear. This plays a louder copy instead, and
              says by how much. The recording itself is never changed — it is what
              the analyzer reads and the only record of what the mic heard.
            </Text>
          </View>
          <Switch
            value={draft.normalizePlayback}
            onValueChange={(normalizePlayback) => commit({ normalizePlayback })}
            trackColor={{ true: colors.accent, false: colors.border }}
          />
        </View>

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>Strict sync</Text>
            <Text style={styles.hint}>
              Refuse to sync when the server is too old to store what this app records.
              A sync that reports success while dropping fields is worse than one that
              stops — turn this off only if landing the audio matters more.
            </Text>
          </View>
          <Switch
            value={draft.strictSync}
            onValueChange={(strictSync) => commit({ strictSync })}
            trackColor={{ true: colors.accent, false: colors.border }}
          />
        </View>

        

        {/* Additive only, and separate from Sync on purpose: sync pushes, this
            pulls, and conflating them is how a stale server copy ends up
            overwriting a field recording. */}
        <View style={styles.restoreBox}>
          <Text style={styles.label}>Restore from server</Text>
          <Text style={styles.hint}>
            Downloads captures this phone doesn&apos;t have. Anything already here is
            left alone, including edits you haven&apos;t synced yet.
          </Text>
          <Pressable
            onPress={restore}
            disabled={busy}
            accessibilityRole="button"
            style={({ pressed }) => [
              styles.action, busy && styles.disabled, pressed && styles.pressed,
            ]}
          >
            <Text style={styles.actionText}>
              {restoring ?? "Restore missing captures"}
            </Text>
          </Pressable>
        </View>

        {/* The other half of working offline. Restore brings back audio this
            phone has lost; this brings down what the analyzer said about the
            audio it already has — which is what makes a timeline in a park
            possible at all. */}
        <View style={styles.restoreBox}>
          <Text style={styles.label}>Analysis for offline</Text>
          <Text style={styles.hint}>
            Stores every synced capture&apos;s detected calls and waveform on the
            phone, so old recordings can be compared against a new one in the
            field. Runs automatically after each sync; this is for when you are
            about to leave and want to be sure.
          </Text>
          <Pressable
            onPress={warmAnalysis}
            disabled={busy}
            accessibilityRole="button"
            style={({ pressed }) => [
              styles.action, busy && styles.disabled, pressed && styles.pressed,
            ]}
          >
            <Text style={styles.actionText}>
              {warming ?? "Download analysis"}
            </Text>
          </Pressable>
        </View>

        <View style={styles.actions}>
          <Pressable
            onPress={() => check("health")}
            disabled={busy}
            style={({ pressed }) => [styles.action, busy && styles.disabled, pressed && styles.pressed]}
          >
            <Text style={styles.actionText}>Test connection</Text>
          </Pressable>
          <Pressable
            onPress={() => check("enroll")}
            disabled={busy}
            style={({ pressed }) => [
              styles.action,
              styles.actionPrimary,
              busy && styles.disabled,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.actionText}>
              {services.isEnrolled ? "Re-enroll" : "Enroll this device"}
            </Text>
          </Pressable>
        </View>

        {message ? <Text style={styles.message}>{message}</Text> : null}

        <IdentityPanel key={enrollments} services={services} />

        <Text style={styles.note}>
          Captures are kept on this phone and are only uploaded when you tap Sync.
        </Text>

        <Pressable
          onPress={onOpenFamilies}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>Families</Text>
        </Pressable>

        <Pressable
          onPress={onOpenPermissions}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>Permissions</Text>
        </Pressable>

        <Pressable
          onPress={onOpenDiagnostics}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>Diagnostics</Text>
        </Pressable>
        <Text style={styles.hint}>
          The audio cues, the earbud button, the mic sources and the app log —
          each of them written for a failure that only happens with the screen
          off, and none of them reproducible on a desk without a page like this.
        </Text>

        <Pressable
          onPress={onOpenLogs}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>App log</Text>
        </Pressable>
        <Text style={styles.hint}>
          Errors and events this phone recorded, readable here without a cable and
          uploaded with the next sync. What to open when something did not work in
          the field and there is no way to say what.
        </Text>

        <BuildFooter />

        {/* Nietzsche, "Vereinsamt". It has no business being in a settings
            screen and it is staying: it is the only four lines anybody has
            written about crows, winter and home at once, which is most of what
            this app is for. */}
        <View style={styles.verse}>
          <Text style={styles.verseText}>
            {"Die Krähen schrein\nund ziehen schwirren Flugs zur Stadt:\n"
              + "bald wird es schnein, —\nwohl dem, der jetzt noch Heimat hat."}
          </Text>
          <Text style={styles.verseBy}>— Nietzsche, „Vereinsamt“</Text>
        </View>
      </KeyboardAwareScroll>
    </View>
  );
}

/**
 * Who this phone belongs to, and how to add another one to the same account.
 *
 * Only meaningful once enrolled — before that there is no account to describe.
 * The claim code is the whole point of the panel: it is what makes a second
 * handset another of *your* devices rather than a stranger with its own corpus.
 */
function IdentityPanel({ services }: { services: AppServices }) {
  const [identity, setIdentity] = useState(services.identity);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    if (!services.isEnrolled) return;
    // Best-effort: the cached identity is what's shown offline, so a failure
    // here is not worth interrupting anyone over.
    services
      .refreshIdentity()
      .then((fresh) => fresh && setIdentity(fresh))
      .catch(() => undefined);
  }, [services]);

  if (!services.isEnrolled || !identity) return null;

  const role = describeRole(identity.role);

  const rotate = async () => {
    setBusy(true);
    setError(undefined);
    try {
      const claimCode = await services.rotateClaimCode();
      setIdentity({ ...identity, claimCode });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.identity}>
      <Text style={styles.label}>
        {identity.contributorName}
        {role ? <Text style={styles.identityRole}> · {role}</Text> : null}
      </Text>
      <Text style={styles.hint}>
        This phone{identity.deviceLabel ? ` — ${identity.deviceLabel}` : ""}
      </Text>

      {identity.claimCode ? (
        <>
          <Text style={styles.claimCode} selectable>
            {identity.claimCode}
          </Text>
          <Text style={styles.hint}>
            Type this into another phone&apos;s Settings before enrolling it, and
            it joins this account instead of starting its own.
          </Text>
        </>
      ) : null}

      <Pressable
        onPress={rotate}
        disabled={busy}
        style={({ pressed }) => [styles.action, busy && styles.disabled, pressed && styles.pressed]}
      >
        <Text style={styles.actionText}>
          {busy ? "Working…" : identity.claimCode ? "New claim code" : "Show claim code"}
        </Text>
      </Pressable>
      <Text style={styles.hint}>
        Replaces the previous code — anything still holding the old one can no
        longer join.
      </Text>
      {error ? <Text style={styles.message}>{error}</Text> : null}
    </View>
  );
}

/**
 * Which build is on this phone.
 *
 * Sits at the bottom of Settings because it is never what you came for and
 * always what you need once something is wrong — the answer to "did the fix
 * actually get installed before I walked out?"
 */
function BuildFooter() {
  const build = currentBuild();
  const committed = formatCommitTime(build);

  return (
    <View style={styles.build}>
      <Text style={[styles.buildVersion, build.dirty && styles.buildDirty]}>
        {formatVersion(build)}
      </Text>
      {committed ? <Text style={styles.buildTime}>{committed}</Text> : null}
      {build.branch && build.branch !== "master" ? (
        <Text style={styles.buildTime}>branch {build.branch}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  verse: {
    // Room on both sides of it. A poem pressed against a build number reads as
    // a stray string rather than as something somebody put there.
    paddingTop: spacing.xl,
    paddingBottom: spacing.xl,
    gap: spacing.sm,
    alignItems: "center",
  },
  verseText: {
    color: colors.textFaint,
    fontSize: 13,
    fontStyle: "italic",
    lineHeight: 20,
    textAlign: "center",
  },
  verseBy: { color: colors.textFaint, fontSize: 11 },
  nested: { paddingLeft: spacing.lg, borderLeftWidth: 2, borderLeftColor: colors.border },
  restoreBox: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingTop: 56, paddingBottom: spacing.sm },
  back: { color: colors.accent, fontSize: 16 },
  pressed: { opacity: 0.6 },
  body: { paddingHorizontal: spacing.lg, paddingBottom: pageEnd, gap: spacing.lg },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  group: { gap: spacing.xs },
  label: { color: colors.text, fontSize: 14, fontWeight: "600" },
  hint: { color: colors.textFaint, fontSize: 12 },
  input: {
    backgroundColor: colors.surface,
    color: colors.text,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 14,
  },
  switchRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  interval: { minWidth: 64, textAlign: "center" },
  switchText: { flex: 1, gap: 2 },
  actions: { flexDirection: "row", gap: spacing.sm },
  action: {
    flex: 1,
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  actionPrimary: { backgroundColor: colors.accent },
  disabled: { opacity: 0.5 },
  actionText: { color: "#fff", fontSize: 14, fontWeight: "700" },
  message: { color: colors.textMuted, fontSize: 13 },
  note: { color: colors.textFaint, fontSize: 12 },
  identity: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
  },
  identityRole: { color: colors.accent, fontWeight: "700" },
  claimCode: {
    color: colors.text,
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    fontSize: 18,
    fontWeight: "700",
    letterSpacing: 1,
    textAlign: "center",
  },
  build: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: 2,
    alignItems: "center",
  },
  buildVersion: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "600",
    fontVariant: ["tabular-nums"],
  },
  buildDirty: { color: colors.accent },
  buildTime: { color: colors.textFaint, fontSize: 11 },
});
