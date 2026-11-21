import { useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { banAddress, decideAccess, liftBan, useAccessRequests } from "../api/client";
import type { AccessRequest, BannedAddress } from "../api/types";
import { formatTime } from "../format";

/** Requests from one address before the address reads as a script. */
const BUSY_ADDRESS = 3;

/**
 * The queue sorted by how likely a row is to be a person.
 *
 * Someone who wants the app says where they would record; a script posting
 * other people's emails does not, and posts many from one address. So: rows
 * with a note first, email-only rows next, everything already answered after
 * that, and at the very bottom whatever came from a banned address or from
 * one that asked BUSY_ADDRESS times or more. An approved row is never filed
 * as spam: an invite somebody holds is not second-guessed by a count.
 */
class Triage {
  readonly perAddress = new Map<string, number>();
  readonly banned: Set<string>;
  readonly noted: AccessRequest[] = [];
  readonly bare: AccessRequest[] = [];
  readonly answered: AccessRequest[] = [];
  readonly spam = new Map<string, AccessRequest[]>();

  constructor(rows: AccessRequest[], banned: BannedAddress[]) {
    this.banned = new Set(banned.map((b) => b.ip));
    for (const row of rows) {
      if (row.requester_ip) {
        this.perAddress.set(row.requester_ip, this.count(row.requester_ip) + 1);
      }
    }
    for (const row of rows) this.file(row);
  }

  count(ip: string): number {
    return this.perAddress.get(ip) ?? 0;
  }

  get pending(): number {
    return this.noted.length + this.bare.length;
  }

  get spamRows(): number {
    return [...this.spam.values()].reduce((sum, rows) => sum + rows.length, 0);
  }

  private suspect(row: AccessRequest): boolean {
    const ip = row.requester_ip;
    if (!ip || row.status === "approved") return false;
    return this.banned.has(ip) || this.count(ip) >= BUSY_ADDRESS;
  }

  private file(row: AccessRequest): void {
    if (this.suspect(row)) {
      const ip = row.requester_ip!;
      this.spam.set(ip, [...(this.spam.get(ip) ?? []), row]);
    } else if (row.status !== "pending") {
      this.answered.push(row);
    } else if (row.note?.trim()) {
      this.noted.push(row);
    } else {
      this.bare.push(row);
    }
  }
}

interface Actions {
  busy: number | string | null;
  decide: (row: AccessRequest, decision: "approve" | "decline") => void;
  copy: (url: string) => void;
  ban: (ip: string, confirmFirst: boolean) => void;
}

/**
 * The queue between "may I try the app?" and an invite.
 *
 * Approving mints the invite link and, when the server has a mailer, emails
 * it; either way the link is here to copy, because the mail may not have
 * gone and because some people are easier to reach by hand. Declined rows
 * stay visible so a repeat request reads as one. Banning an address declines
 * what it has pending and stops the public forms taking anything more from it.
 */
export function AccessPage({ signedIn }: { signedIn: boolean }) {
  const queue = useAccessRequests(signedIn);
  const queries = useQueryClient();
  const [busy, setBusy] = useState<number | string | null>(null);
  const [note, setNote] = useState<string | undefined>();

  const attempt = async (key: number | string, work: () => Promise<string | undefined>) => {
    setBusy(key);
    setNote(undefined);
    try {
      setNote(await work());
      await queries.invalidateQueries({ queryKey: ["access"] });
    } catch (failure) {
      setNote(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(null);
    }
  };

  const decide = (row: AccessRequest, decision: "approve" | "decline") =>
    void attempt(row.id, async () => {
      const result = await decideAccess(row.id, decision);
      if (decision !== "approve") return undefined;
      if (result.emailed) return `Invite emailed to ${row.email}.`;
      return result.request.email_error
        ? `Approved, but the email failed: ${result.request.email_error}. Copy the link instead.`
        : "Approved. No mailer is configured, so copy the link and send it yourself.";
    });

  const ban = (ip: string, confirmFirst: boolean) => {
    if (confirmFirst && !window.confirm(`Ban ${ip}? Its pending requests are declined.`)) return;
    void attempt(ip, async () => {
      const result = await banAddress(ip);
      return `Banned ${ip}; ${result.declined} pending request${result.declined === 1 ? "" : "s"} declined.`;
    });
  };

  const unban = (ip: string) =>
    void attempt(ip, async () => {
      await liftBan(ip);
      return `${ip} may use the forms again.`;
    });

  const copy = (url: string) =>
    void navigator.clipboard.writeText(url).then(
      () => setNote("Link copied."),
      () => setNote(url),
    );

  const banned = queue.data?.banned ?? [];
  const triage = new Triage(queue.data?.requests ?? [], banned);
  const actions: Actions = { busy, decide, copy, ban };

  return (
    <>
      <div className="card">
        <h2>Access requests{triage.pending ? ` · ${triage.pending} to read` : ""}</h2>
        <div className="note">
          {queue.data?.build ?? "…"}
          {queue.data
            ? queue.data.mail_configured
              ? " Approving emails the invite."
              : " No mailer configured: approving gives you a link to send by hand."
            : null}
          {" "}
          Requests come in at /preview.
        </div>
        {note ? <div className="note">{note}</div> : null}
      </div>

      <Section
        title="With a note"
        hint="They said where they would record. Most likely people."
        rows={triage.noted}
        empty={queue.isPending ? "Loading…" : "Nothing waiting with a note."}
        triage={triage}
        actions={actions}
      />
      <Section
        title="Email only"
        hint="No note. Could be a person in a hurry, could be the start of a flood."
        rows={triage.bare}
        empty="Nothing waiting without a note."
        triage={triage}
        actions={actions}
      />
      <Section
        title="Answered"
        hint="Approved and declined."
        rows={triage.answered}
        empty="Nothing answered yet."
        triage={triage}
        actions={actions}
      />

      <div className="card">
        <h2>Probably spam{triage.spamRows ? ` · ${triage.spamRows}` : ""}</h2>
        <div className="note">
          From a banned address, or from one that asked {BUSY_ADDRESS} times or more. Never approve
          these: approving sends an email to someone who did not ask for it.
        </div>
        {triage.spam.size === 0 ? <div className="muted">Nothing here.</div> : null}
        {[...triage.spam.entries()]
          .sort((a, b) => b[1].length - a[1].length)
          .map(([ip, rows]) => (
            <details key={ip}>
              <summary>
                {ip} · {rows.length} request{rows.length === 1 ? "" : "s"}{" "}
                {triage.banned.has(ip) ? (
                  <span className="muted">banned</span>
                ) : (
                  <button onClick={() => ban(ip, false)} disabled={busy === ip}>
                    Ban address
                  </button>
                )}
              </summary>
              <RequestTable rows={rows} triage={triage} actions={actions} />
            </details>
          ))}
      </div>

      <div className="card">
        <h2>Banned addresses{banned.length ? ` · ${banned.length}` : ""}</h2>
        <div className="note">
          The access form and the Scan page take nothing from these. A banned script still sees the
          thank-you page, so it has no reason to move.
        </div>
        <BanForm onBan={(ip) => ban(ip, false)} />
        {banned.length === 0 ? <div className="muted">No address is banned.</div> : null}
        {banned.map((address) => (
          <div key={address.ip}>
            {address.ip}{" "}
            <span className="muted">
              · {address.requests} request{address.requests === 1 ? "" : "s"} · banned{" "}
              {formatTime(address.banned_at)}
            </span>{" "}
            <button className="ghost" onClick={() => unban(address.ip)} disabled={busy === address.ip}>
              Unban
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

function BanForm({ onBan }: { onBan: (ip: string) => void }) {
  const [ip, setIp] = useState("");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (ip.trim()) onBan(ip.trim());
        setIp("");
      }}
    >
      <input
        value={ip}
        onChange={(event) => setIp(event.target.value)}
        placeholder="An address, e.g. 203.0.113.9"
      />{" "}
      <button type="submit" disabled={!ip.trim()}>
        Ban
      </button>
    </form>
  );
}

function Section(props: {
  title: string;
  hint: string;
  rows: AccessRequest[];
  empty: string;
  triage: Triage;
  actions: Actions;
}): ReactNode {
  return (
    <div className="card">
      <h2>
        {props.title}
        {props.rows.length ? ` · ${props.rows.length}` : ""}
      </h2>
      <div className="note">{props.hint}</div>
      {props.rows.length === 0 ? (
        <div className="muted">{props.empty}</div>
      ) : (
        <RequestTable rows={props.rows} triage={props.triage} actions={props.actions} />
      )}
    </div>
  );
}

function RequestTable({
  rows,
  triage,
  actions,
}: {
  rows: AccessRequest[];
  triage: Triage;
  actions: Actions;
}) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Who</th>
            <th>Asked</th>
            <th>From</th>
            <th>Status</th>
            <th>Invite</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <RequestRow key={row.id} row={row} triage={triage} actions={actions} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RequestRow({
  row,
  triage,
  actions,
}: {
  row: AccessRequest;
  triage: Triage;
  actions: Actions;
}) {
  const ip = row.requester_ip;
  const waiting = actions.busy === row.id;
  return (
    <tr>
      <td>
        {row.name ? <>{row.name} · </> : null}
        {row.email}
        {row.note ? <div className="muted">{row.note}</div> : null}
      </td>
      <td className="muted">{formatTime(row.requested_at)}</td>
      <td className="muted">
        {ip ?? "—"}
        {ip && triage.count(ip) > 1 ? <div>{triage.count(ip)} requests from here</div> : null}
        {ip && !triage.banned.has(ip) ? (
          <div>
            <button
              className="ghost"
              onClick={() => actions.ban(ip, true)}
              disabled={actions.busy === ip}
            >
              Ban
            </button>
          </div>
        ) : null}
      </td>
      <td>
        {row.status}
        {row.status === "approved" ? (
          <div className="muted">
            {row.emailed_at
              ? `emailed ${formatTime(row.emailed_at)}`
              : row.email_error
                ? `email failed: ${row.email_error}`
                : "not emailed"}
            {row.downloads
              ? ` · ${row.downloads} download${row.downloads === 1 ? "" : "s"}`
              : " · not downloaded"}
          </div>
        ) : null}
      </td>
      <td>
        {row.invite_url ? (
          <button className="ghost" onClick={() => actions.copy(row.invite_url!)}>
            Copy link
          </button>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td>
        {row.status !== "declined" ? (
          <>
            <button onClick={() => actions.decide(row, "approve")} disabled={waiting}>
              {row.status === "approved" ? "Resend" : "Approve"}
            </button>{" "}
            <button
              className="ghost"
              onClick={() => actions.decide(row, "decline")}
              disabled={waiting}
            >
              Decline
            </button>
          </>
        ) : null}
      </td>
    </tr>
  );
}
