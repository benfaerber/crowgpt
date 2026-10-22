import { useState } from "react";

import { hasRememberedSecret, signIn } from "../api/client";

/**
 * Exchange the operator secret for a session.
 *
 * The operator holds the *operator token*; every request needs a *device
 * bearer token*. Making someone paste one and then discover they needed the
 * other is the trap people actually fell into, so the exchange happens here and
 * the field is labelled with the name of the thing they were given.
 */
export function SignIn({
  reason,
  onSignedIn,
}: {
  reason?: string;
  onSignedIn: () => void;
}) {
  const [token, setToken] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | undefined>(reason);
  const [busy, setBusy] = useState(false);

  const connect = async () => {
    setBusy(true);
    setError(undefined);
    try {
      await signIn(token.trim(), remember);
      onSignedIn();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>Operator token</h2>
      <p className="muted" style={{ fontSize: ".88rem", marginTop: 0 }}>
        Paste the <strong>operator token</strong> printed by{" "}
        <code>make -C fieldserver secrets</code>. Exchanged for a session token
        kept in this browser only.
        {hasRememberedSecret() ? " A saved token was rejected — this fleet's secret has changed." : ""}
      </p>
      <form
        style={{ display: "flex", gap: ".6rem", flexWrap: "wrap" }}
        onSubmit={(event) => {
          event.preventDefault();
          void connect();
        }}
      >
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="operator token"
          style={{ flex: 1, minWidth: "16rem" }}
          autoFocus
        />
        <button type="submit" disabled={busy || token.trim() === ""}>
          {busy ? "Connecting…" : "Connect"}
        </button>
      </form>

      {/* Checked by default: the dashboard is what you open to find things out,
          not a login to fight, and this is a home network. It stores the fleet's
          master secret in this browser, so untick it before the dashboard is
          ever reachable from outside — a script on the page could read it,
          where a session token is at least revocable. */}
      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: ".5rem",
          marginTop: ".7rem",
          fontSize: ".85rem",
          color: "var(--muted)",
        }}
      >
        <input
          type="checkbox"
          checked={remember}
          onChange={(event) => setRemember(event.target.checked)}
        />
        Stay signed in on this browser
      </label>
      {error ? <div className="note">{error}</div> : null}
    </div>
  );
}
