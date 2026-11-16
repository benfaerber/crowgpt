import { Component, type ReactNode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { LabelingScreen } from "../../src/ui/LabelingScreen";
import { colors, radius, spacing } from "../../src/ui/theme";

import { DeskApi, DeskError, type Desk } from "./DeskApi";
import { stageMediaElement } from "./shims/expo-audio";
import { ScanDeskServices } from "./ScanDeskServices";

const SITE = "https://crowgpt.org";

/**
 * The Scan page the visitor came from, which the link to here names after
 * `#from=`. Believed only when it is the project's site or this server's own
 * copy of it; anything else gets the public Scan page.
 */
function scanPage(): string {
  const fallback = `${SITE}/scan`;
  try {
    const from = new URLSearchParams(window.location.hash.slice(1)).get("from");
    if (!from) return fallback;
    const url = new URL(from);
    const trusted = [new URL(SITE).origin, "https://www.crowgpt.org", window.location.origin];
    return trusted.includes(url.origin) ? url.origin + url.pathname : fallback;
  } catch {
    return fallback;
  }
}

const SCAN_PAGE = scanPage();

type Loaded =
  | { state: "loading" }
  | { state: "missing" }
  | { state: "failed"; message: string }
  | { state: "ready"; desk: Desk };

/** /label/<public id>: the id is the last segment, whatever serves the page. */
function publicIdFromLocation(): string {
  return window.location.pathname.split("/").filter(Boolean).pop() ?? "";
}

/**
 * The labelling desk for a recording someone uploaded to the Scan page.
 *
 * The desk itself is the phone's LabelingScreen. This file is only what a
 * browser needs around it: finding the recording from the link, a column to
 * sit in, and what to say before and after.
 */
function ScanDesk() {
  const api = useMemo(() => new DeskApi(publicIdFromLocation()), []);
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [failure, setFailure] = useState<string>();
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    api.load().then(
      (desk) => setLoaded({ state: "ready", desk }),
      (error) =>
        setLoaded(
          error instanceof DeskError && error.status === 404
            ? { state: "missing" }
            : { state: "failed", message: error instanceof Error ? error.message : String(error) },
        ),
    );
  }, [api]);

  const services = useMemo(
    () => (loaded.state === "ready" ? new ScanDeskServices(api, loaded.desk, setFailure) : undefined),
    [api, loaded],
  );

  // A video scan plays through a <video> the page owns, staged before the
  // desk makes its player, so "Play this call" shows the clip as well.
  const picture = useMemo(() => {
    if (loaded.state !== "ready" || loaded.desk.kind !== "video") return undefined;
    const video = document.createElement("video");
    video.playsInline = true;
    video.preload = "auto";
    Object.assign(video.style, {
      display: "block", width: "100%", maxHeight: "38vh", background: "#000", objectFit: "contain",
    });
    stageMediaElement(video);
    return video;
  }, [loaded]);

  if (loaded.state === "loading") return <Notice title="Finding your recording…" />;
  if (loaded.state === "missing") {
    return (
      <Notice
        title="This link does not open a recording"
        body="Labelling is for a recording or video you scanned and let CrowGPT keep. The link is on the scan's result."
        action={{ label: "Scan a recording", href: SCAN_PAGE }}
      />
    );
  }
  if (loaded.state === "failed" || !services) {
    return <Notice title="Could not load this recording" body={loaded.state === "failed" ? loaded.message : ""} />;
  }
  if (loaded.desk.closed) {
    return (
      <Notice
        title="This recording has been reviewed"
        body="Someone on the project has listened to it and taken your labels with it, so they are final. Thank you."
        action={{ label: "Back to your scans", href: SCAN_PAGE }}
      />
    );
  }
  if (finished) {
    return (
      <Notice
        title="Thank you"
        body={
          services.decided > 0
            ? `${services.decided} ${services.decided === 1 ? "call" : "calls"} labelled. What you heard and what was happening is the part no model can supply.`
            : "Nothing is labelled yet. You can come back to this link whenever you like."
        }
        action={{ label: "Back to your scan", href: SCAN_PAGE }}
        more={{ label: "Get the field app", href: `${SITE}/#request` }}
        back={{ label: "Keep labelling", onPress: () => setFinished(false) }}
      />
    );
  }

  return (
    <View style={styles.page}>
      <View style={styles.column}>
        {failure ? (
          <Pressable onPress={() => setFailure(undefined)} style={styles.failure}>
            <Text style={styles.failureText}>Not saved: {failure}</Text>
          </Pressable>
        ) : null}
        {picture ? <Picture video={picture} /> : null}
        <LabelingScreen services={services} capture={services.capture} onBack={() => setFinished(true)} />
      </View>
    </View>
  );
}

/** The staged <video>, put on the page. */
function Picture({ video }: { video: HTMLVideoElement }) {
  return (
    <div
      ref={(host) => {
        if (host && video.parentElement !== host) host.replaceChildren(video);
      }}
    />
  );
}

function Notice({
  title,
  body,
  action,
  more,
  back,
}: {
  title: string;
  body?: string;
  action?: { label: string; href: string };
  more?: { label: string; href: string };
  back?: { label: string; onPress: () => void };
}) {
  return (
    <View style={styles.page}>
      <View style={[styles.column, styles.notice]}>
        <Text style={styles.title}>{title}</Text>
        {body ? <Text style={styles.body}>{body}</Text> : null}
        {back ? (
          <Pressable onPress={back.onPress} style={styles.button}>
            <Text style={styles.buttonText}>{back.label}</Text>
          </Pressable>
        ) : null}
        {action ? (
          <Pressable accessibilityRole="link" onPress={() => window.location.assign(action.href)}>
            <Text style={styles.link}>{action.label}</Text>
          </Pressable>
        ) : null}
        {more ? (
          <Pressable accessibilityRole="link" onPress={() => window.location.assign(more.href)}>
            <Text style={styles.link}>{more.label}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, alignItems: "center", backgroundColor: colors.background },
  column: { flex: 1, width: "100%", maxWidth: 520 },
  notice: { justifyContent: "center", padding: spacing.lg, gap: spacing.md },
  title: { color: colors.text, fontSize: 22, fontWeight: "700" },
  body: { color: colors.textMuted, fontSize: 15, lineHeight: 22 },
  button: {
    backgroundColor: colors.accent,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  buttonText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  link: { color: colors.accent, fontSize: 15, textAlign: "center" },
  failure: { backgroundColor: "#4a1f1f", padding: spacing.sm },
  failureText: { color: "#ffd9d9", fontSize: 13, textAlign: "center" },
});

/** A render that throws says so, where it used to leave an empty page. */
class Failsafe extends Component<{ children: ReactNode }, { failed?: string }> {
  state: { failed?: string } = {};

  static getDerivedStateFromError(error: unknown) {
    return { failed: error instanceof Error ? error.message : String(error) };
  }

  render() {
    return this.state.failed === undefined ? (
      this.props.children
    ) : (
      <Notice title="The labelling desk hit a problem" body={`Reload to try again. (${this.state.failed})`} />
    );
  }
}

const root = document.getElementById("root");
if (root) {
  root.style.display = "flex";
  createRoot(root).render(
    <Failsafe>
      <ScanDesk />
    </Failsafe>,
  );
}
