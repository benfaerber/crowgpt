import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import {
  fetchGenerationAudioUrl,
  forgetGenerations,
  requestGeneration,
  useGenerations,
} from "../api/client";
import type { ChatModel, Generation } from "../api/types";

/**
 * Chat with CrowGPT: pick a model, press a call-type button, the request
 * appears as your message, and the generated clip arrives as the reply bubble.
 *
 * The models and their buttons come from the server rather than being written
 * here, so the page cannot offer a model or a type the queue would refuse. A
 * model with no call types (the releases) takes a single bare "caw" request.
 * The thread is just the `generations` table in id order — a reload, another
 * browser, or tomorrow all see the same conversation, because the conversation
 * *is* the table.
 */

const REQUEST_LINE: Record<string, string> = {
  "alarm call": "An alarm call, please.",
  begging: "Some begging, please.",
  call: "A normal call, please.",
  song: "A song, please.",
};

const CAW_LINE = "A caw, please — your choice.";

const MODEL_LABEL: Record<string, string> = {
  crowgpt1: "CrowGPT1",
  crowgpt2: "CrowGPT2",
  "model-longctx-ct": "CrowGPT3 candidate (old)",
  "model-longctx-ct-b32": "CrowGPT3 candidate",
};

function modelLabel(name: string): string {
  return MODEL_LABEL[name] ?? name;
}

function GeneratedAudio({ generation }: { generation: Generation }) {
  const [url, setUrl] = useState<string>();
  const [error, setError] = useState<string>();

  // The blob-URL dance from AudioPanel: <audio src> cannot carry the bearer
  // header, so fetch with it and hand the element an object URL instead.
  useEffect(() => {
    let created: string | undefined;
    let gone = false;
    fetchGenerationAudioUrl(generation.id)
      .then((u) => {
        created = u;
        if (gone) URL.revokeObjectURL(u);
        else setUrl(u);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    return () => {
      gone = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [generation.id]);

  if (error) return <span className="chat-error">could not load the clip — {error}</span>;
  if (!url) return <span className="chat-meta">loading the clip…</span>;
  return <audio controls src={url} />;
}

function Exchange({ generation }: { generation: Generation }) {
  return (
    <li className="chat-exchange">
      <div className="chat-bubble chat-ask">
        {generation.call_type
          ? REQUEST_LINE[generation.call_type] ?? generation.call_type
          : CAW_LINE}
      </div>
      <span className="chat-meta chat-ask-meta">
        to {modelLabel(generation.model)}
      </span>
      <div className="chat-bubble chat-reply">
        {generation.state === "done" ? (
          <>
            <GeneratedAudio generation={generation} />
            <span className="chat-meta">
              {generation.call_type ?? "caw"} · {generation.duration_sec?.toFixed(1)}s ·
              seed {generation.seed} · {modelLabel(generation.model)}
            </span>
          </>
        ) : generation.state === "failed" ? (
          <span className="chat-error">
            The model could not answer — {generation.error}
          </span>
        ) : (
          <span className="chat-typing" aria-label="generating">
            <span /><span /><span />
          </span>
        )}
      </div>
    </li>
  );
}

export function CrowChatPage({ signedIn }: { signedIn: boolean }) {
  const feed = useGenerations(signedIn);
  const queryClient = useQueryClient();
  const [sending, setSending] = useState(false);
  const [failure, setFailure] = useState<string>();
  const [modelName, setModelName] = useState("model-calltype");
  const endRef = useRef<HTMLDivElement>(null);

  const generations = feed.data?.generations ?? [];
  const models = feed.data?.models ?? [];
  const model: ChatModel | undefined =
    models.find((m) => m.name === modelName) ?? models[0];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [generations.length]);

  async function ask(callType?: string) {
    if (!model) return;
    setSending(true);
    setFailure(undefined);
    try {
      await requestGeneration(model.name, callType);
      await queryClient.invalidateQueries({ queryKey: ["generations"] });
    } catch (e) {
      setFailure(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  function forget() {
    if (!confirm("Forget the whole conversation? The clips and their seeds go with it.")) return;
    setFailure(undefined);
    forgetGenerations()
      .then(() => queryClient.invalidateQueries({ queryKey: ["generations"] }))
      .catch((e) => setFailure(e instanceof Error ? e.message : String(e)));
  }

  return (
    <div className="card">
      <div className="chat-head">
        <h2>Crow Chat</h2>
        <span className="spacer" />
        <button
          className="ghost"
          title="Delete every exchange and its clip. Synthetic audio only — nothing kept here."
          disabled={generations.length === 0}
          onClick={forget}
        >
          Forget
        </button>
      </div>
      <p className="note">
        Ask for a call and CrowGPT answers with one, generated on the spot.
        model-calltype is the checkpoint that takes call-type requests; the
        releases answer a bare caw their own way. Synthetic audio; nothing here
        is, or ever becomes, a capture.
      </p>
      {generations.length === 0 && !feed.isPending ? (
        <p className="chat-empty">Nothing asked yet. The buttons below start the conversation.</p>
      ) : (
        <ul className="chat-thread">
          {generations.map((g) => (
            <Exchange key={g.id} generation={g} />
          ))}
        </ul>
      )}
      <div ref={endRef} />
      {failure ? <p className="chat-error">Could not ask — {failure}</p> : null}
      <div className="chat-models" role="radiogroup" aria-label="model">
        {models.map((m) => (
          <button
            key={m.name}
            className={m.name === model?.name ? "chat-model on" : "chat-model"}
            aria-pressed={m.name === model?.name}
            onClick={() => setModelName(m.name)}
          >
            {modelLabel(m.name)}
          </button>
        ))}
      </div>
      <div className="chat-buttons">
        {model && model.call_types.length === 0 ? (
          <button disabled={sending} onClick={() => void ask()}>
            caw
          </button>
        ) : (
          (model?.call_types ?? []).map((t) => (
            <button key={t} disabled={sending} onClick={() => void ask(t)}>
              {t}
            </button>
          ))
        )}
      </div>
    </div>
  );
}
