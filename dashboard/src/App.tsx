import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  ApiError,
  clearToken,
  hasRememberedSecret,
  recoverSession,
  storedToken,
  useFleet,
  useServerBuild,
} from "./api/client";
import { BUNDLE, formatBuild, isStale, type ServerBuild } from "./buildInfo";
import { presentationMode, setPresentationMode } from "./format";
import { PAGES, usePage, type Page } from "./page";
import { CapturesPage } from "./components/CapturesPage";
import { ContributorsPanel } from "./components/ContributorsPanel";
import { CrowChatPage } from "./components/CrowChatPage";
import { DevicesPanel } from "./components/DevicesPanel";
import { FamiliesPanel } from "./components/FamiliesPanel";
import { FamilyDetail } from "./components/FamilyDetail";
import { LabelTotals } from "./components/LabelTotals";
import { ListeningPanel } from "./components/ListeningPanel";
import { LogsPanel } from "./components/LogsPanel";
import { RelabelPanel } from "./components/RelabelPanel";
import { TrainingPanel } from "./components/TrainingPanel";
import { CorpusPanel } from "./components/CorpusPanel";
import { SemanticsPanel } from "./components/SemanticsPanel";
import { SignIn } from "./components/SignIn";
import { Tiles } from "./components/Tiles";
import { UploadDropzone } from "./components/UploadDropzone";

export function App() {
  // Signed-in is state, not something derived from whether a query happens to
  // be holding an error. Deriving it meant a successful sign-in left the gate
  // up — the old errors were still on the queries, so the only way through was
  // a manual reload.
  const [signedIn, setSignedIn] = useState(() => storedToken() !== "");
  const [reason, setReason] = useState<string>();
  const [recovering, setRecovering] = useState(false);
  // Captures moved to their own page and open in place, so the only thing left
  // for the overview to expand is a family.
  const [selectedFamily, setSelectedFamily] = useState<number>();
  const [page, setPage] = usePage();
  // Held here rather than in the header so the panels re-render when it flips:
  // the masking is read while a row is drawn, and a switch nothing observes is
  // a switch that appears not to work.
  const [presentation, setPresentation] = useState(presentationMode());
  const queries = useQueryClient();
  const fleet = useFleet(signedIn);
  // Unauthenticated, so it resolves on the sign-in screen too.
  const serverBuild = useServerBuild();

  // One rejected request means the whole session is dead, not just that panel.
  const rejected = Object.values(fleet).find(
    (query) => query.error instanceof ApiError && query.error.isAuthFailure,
  )?.error as ApiError | undefined;

  useEffect(() => {
    if (!rejected || !signedIn || recovering) return;
    setRecovering(true);
    // A remembered secret lets the dashboard let itself back in rather than
    // asking again for something it already knows.
    void recoverSession()
      .then((recovered) => {
        if (recovered) {
          void queries.refetchQueries();
        } else {
          setSignedIn(false);
          setReason(rejected.message);
        }
      })
      .finally(() => setRecovering(false));
  }, [rejected, signedIn, recovering, queries]);

  const signOut = () => {
    clearToken();
    queries.clear();
    setSelectedFamily(undefined);
    setReason(undefined);
    setSignedIn(false);
  };

  if (!signedIn) {
    return (
      <Shell build={serverBuild.data}>
        <SignIn
          reason={reason}
          onSignedIn={() => {
            setReason(undefined);
            setSignedIn(true);
            // Cached failures belong to the dead session; drop them or the
            // panels render their old errors under a working one.
            void queries.resetQueries();
          }}
        />
      </Shell>
    );
  }

  if (rejected && recovering) {
    return (
      <Shell build={serverBuild.data}>
        <div className="card muted">Signing back in…</div>
      </Shell>
    );
  }

  const failure = Object.values(fleet).find(
    (query) => query.error && !(query.error instanceof ApiError && query.error.isAuthFailure),
  )?.error;

  return (
    <Shell
      build={serverBuild.data}
      presentation={presentation}
      onPresentation={(on) => {
        setPresentationMode(on);
        setPresentation(on);
      }}
      configVersion={fleet.summary.data?.config_version}
      onRefresh={() => void queries.invalidateQueries()}
      onSignOut={signOut}
      page={page}
      onPage={setPage}
    >
      {failure ? (
        <div className="card">
          <div className="note">Could not reach the server — {failure.message}</div>
        </div>
      ) : null}

      {page === "captures" ? (
        <CapturesPage
          key={presentation ? "masked" : "plain"}
          captures={fleet.captures.data ?? []}
          loading={fleet.captures.isPending}
        />
      ) : page === "progress" ? (
        <TrainingPanel signedIn={signedIn} />
      ) : page === "corpus" ? (
        <CorpusPanel signedIn={signedIn} />
      ) : page === "chat" ? (
        <CrowChatPage signedIn={signedIn} />
      ) : page === "logs" ? (
        <LogsPanel />
      ) : (
        <>
          <div className="card">
            <h2>Fleet</h2>
            <Tiles summary={fleet.summary.data} />
          </div>

          <UploadDropzone />

          {selectedFamily !== undefined ? (
            <FamilyDetail familyId={selectedFamily} />
          ) : null}

          <SemanticsPanel matrix={fleet.semantics.data} />

          <div className="grid2" key={presentation ? "masked-grid" : "plain-grid"}>
            <ContributorsPanel contributors={fleet.contributors.data ?? []} />
            <DevicesPanel devices={fleet.devices.data ?? []} />
            <FamiliesPanel
              families={fleet.families.data ?? []}
              selectedId={selectedFamily}
              onSelect={(id) =>
                setSelectedFamily((current) => (current === id ? undefined : id))
              }
            />
            <LabelTotals totals={fleet.labels.data ?? []} />
            <RelabelPanel signedIn={signedIn} />
            {/* Beside Relabel rather than up with Progress Monitor: both are jobs
                waiting on a person, and unlike those jobs this one is a standing
                queue rather than something that runs for a few hours a week. */}
            <ListeningPanel signedIn={signedIn} />
          </div>
        </>
      )}
    </Shell>
  );
}

function Shell({
  children,
  build,
  presentation = false,
  onPresentation,
  configVersion,
  onRefresh,
  onSignOut,
  page,
  onPage,
}: {
  children: React.ReactNode;
  /** True while precise locations are hidden for screenshots. */
  presentation?: boolean;
  onPresentation?: (on: boolean) => void;
  /** What the server is running. Undefined until /api/health answers. */
  build?: ServerBuild;
  configVersion?: number;
  onRefresh?: () => void;
  onSignOut?: () => void;
  /** Absent on the sign-in screen, which has nowhere to navigate to. */
  page?: Page;
  onPage?: (page: Page) => void;
}) {
  const stale = isStale(build);
  return (
    <>
      <header>
        <h1>🐦‍⬛ Cawtalker Field Server</h1>
        <span className="tag sub">
          Fleet command &amp; control — captures, calls, and ground truth
        </span>
        {page && onPage ? (
          <nav className="pages">
            {(Object.keys(PAGES) as Page[]).map((name) => (
              <button
                key={name}
                className={name === page ? "ghost on" : "ghost"}
                aria-current={name === page ? "page" : undefined}
                onClick={() => onPage(name)}
              >
                {PAGES[name]}
              </button>
            ))}
            {/* An anchor, not a Page: /listen/ is a separate page fieldserver
                serves, so a hash route to it would render nothing and a real
                path would 404 on reload. */}
            <a className="ghost" href="/listen/">
              Listen
            </a>
            <a className="ghost" href="/gallery/">
              Gallery
            </a>
          </nav>
        ) : null}
        <span className="spacer" />
        {configVersion !== undefined ? (
          <span className="tag">config v{configVersion}</span>
        ) : null}
        {/* The number a sync's honesty turns on. Shown beside the config
            version because they are read together and mean different things:
            the config version says which vocabulary a phone was served, this
            says what the server can store of what comes back. An operator
            reading a capture with fields missing has no other way to see it. */}
        {build?.wire !== undefined ? (
          <span
            className="tag"
            title="What this server can store. A phone sending a field a lower-wire server does not know about has it accepted and discarded."
          >
            wire v{build.wire}
          </span>
        ) : null}
        {build ? (
          <span
            className="tag"
            title={`server ${formatBuild(build)}${
              build.branch ? ` on ${build.branch}` : ""
            }${build.committed_at ? ` — committed ${build.committed_at}` : ""}`}
          >
            {formatBuild(build)}
          </span>
        ) : null}
        {/* Only when this page is *behind* the server. Ahead is routine in dev —
            Vite serves the working tree against a Flask process started from an
            older commit — and flagging that would train the eye past the warning
            that matters. */}
        {stale ? (
          <span
            className="tag warn"
            title={`This page was built at ${formatBuild(BUNDLE)}. Reload to pick up the server's.`}
          >
            page v{BUNDLE.version} — reload
          </span>
        ) : null}
        {/* For the screenshot. Contributors with censored coordinates are
            masked regardless; this covers everyone else in one switch, so a
            promo image cannot give away somebody's street by omission. */}
        {onPresentation ? (
          <button
            className="ghost"
            title="Hide precise coordinates everywhere on this page, for screenshots"
            onClick={() => onPresentation(!presentation)}
          >
            {presentation ? "📷 Locations hidden" : "Hide locations"}
          </button>
        ) : null}
        {onRefresh ? (
          <button className="ghost" onClick={onRefresh}>
            Refresh
          </button>
        ) : null}
        {onSignOut ? (
          <button className="ghost" onClick={onSignOut} title={
            hasRememberedSecret() ? "Also forgets the saved operator token" : undefined
          }>
            Sign out
          </button>
        ) : null}
      </header>
      <main>{children}</main>
    </>
  );
}
