import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { decideAccess, useAccessRequests } from "../api/client";
import type { AccessRequest } from "../api/types";
import { formatTime } from "../format";

/**
 * The queue between "may I try the app?" and an invite.
 *
 * Approving mints the invite link and, when the server has a mailer, emails
 * it; either way the link is here to copy, because the mail may not have
 * gone and because some people are easier to reach by hand. Declined rows
 * stay visible so a repeat request reads as one.
 */
export function AccessPage({ signedIn }: { signedIn: boolean }) {
  const queue = useAccessRequests(signedIn);
  const queries = useQueryClient();
  const [busy, setBusy] = useState<number | null>(null);
  const [note, setNote] = useState<string | undefined>();

  const decide = async (row: AccessRequest, decision: "approve" | "decline") => {
    setBusy(row.id);
    setNote(undefined);
    try {
      const result = await decideAccess(row.id, decision);
      if (decision === "approve") {
        setNote(
          result.emailed
            ? `Invite emailed to ${row.email}.`
            : result.request.email_error
              ? `Approved, but the email failed: ${result.request.email_error}. Copy the link instead.`
              : "Approved. No mailer is configured, so copy the link and send it yourself.",
        );
      }
      await queries.invalidateQueries({ queryKey: ["access"] });
    } catch (failure) {
      setNote(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(null);
    }
  };

  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setNote("Link copied.");
    } catch {
      setNote(url);
    }
  };

  const rows = queue.data?.requests ?? [];
  const pending = rows.filter((r) => r.status === "pending").length;

  return (
    <div className="card">
      <h2>Access requests{pending ? ` · ${pending} pending` : ""}</h2>
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
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Who</th>
              <th>Asked</th>
              <th>Status</th>
              <th>Invite</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  {queue.isPending ? "Loading…" : "Nobody has asked yet."}
                </td>
              </tr>
            ) : null}
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  {row.name ? <>{row.name} · </> : null}
                  {row.email}
                  {row.note ? <div className="muted">{row.note}</div> : null}
                </td>
                <td className="muted">{formatTime(row.requested_at)}</td>
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
                    <button className="ghost" onClick={() => void copy(row.invite_url!)}>
                      Copy link
                    </button>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  {row.status !== "declined" ? (
                    <button
                      onClick={() => void decide(row, "approve")}
                      disabled={busy === row.id}
                    >
                      {row.status === "approved" ? "Resend" : "Approve"}
                    </button>
                  ) : null}{" "}
                  {row.status !== "declined" ? (
                    <button
                      className="ghost"
                      onClick={() => void decide(row, "decline")}
                      disabled={busy === row.id}
                    >
                      Decline
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
