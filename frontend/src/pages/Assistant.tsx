import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Button, ErrorNotice, Notice, PageHeader, Pill } from "../components/ui";
import { api } from "../lib/api";
import type { Reply } from "../lib/types";

type Msg = { role: "user" | "assistant"; text: string; reply?: Reply; image?: string };
const SRC_LABEL: Record<string, string> = { model_observation: "Model observation", database_fact: "Database fact", user_provided: "You said", generated: "AI-generated" };

export default function Assistant() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  const send = useMutation({
    mutationFn: async (v: { text: string; image: File | null; audio: Blob | null }) => {
      if (v.audio) { const f = new FormData(); f.append("file", v.audio, "voice.webm"); return api<Reply>("/assistant/audio", { form: f }); }
      if (v.image) { const f = new FormData(); f.append("file", v.image); f.append("text", v.text); return api<Reply>("/assistant/multimodal", { form: f }); }
      return api<Reply>("/assistant/message", { json: { text: v.text } });
    },
    onSuccess: (r) => setMsgs((m) => [...m, ...(r.transcript ? [{ role: "user" as const, text: `🎤 ${r.transcript}` }] : []), { role: "assistant", text: r.reply, reply: r }]),
  });

  const submit = () => {
    if (!text.trim() && !image) return;
    setMsgs((m) => [...m, { role: "user", text: text || "(photo)", image: image ? URL.createObjectURL(image) : undefined }]);
    send.mutate({ text, image, audio: null });
    setText(""); setImage(null);
  };

  const toggleMic = async () => {
    setMicError(null);
    if (recording) { rec.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => chunks.current.push(e.data);
      mr.onstop = () => { stream.getTracks().forEach((t) => t.stop()); setRecording(false); send.mutate({ text: "", image: null, audio: new Blob(chunks.current, { type: "audio/webm" }) }); };
      mr.start(); rec.current = mr; setRecording(true);
    } catch { setMicError("Microphone unavailable. Allow microphone access, or type your question instead."); }
  };

  return (
    <>
      <PageHeader title="Assistant" intro="Ask about nutrition, ask for a recipe, or attach a food photo. Answers show where each fact came from." />
      <div className="space-y-3" aria-live="polite">
        {msgs.length === 0 && <Notice>Try: “how many calories are in 200 g of banana?”, “recipe with rice and tomatoes”, or attach a photo and ask “what is this?”</Notice>}
        {msgs.map((m, i) => (
          <div key={i} className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${m.role === "user" ? "ml-auto bg-leaf text-white" : "border border-line bg-card"}`}>
            {m.image && <img src={m.image} alt="Attached" className="mb-2 max-h-40 rounded" />}
            <p>{m.text}</p>
            {m.reply && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {m.reply.sources.map((s, k) => <span key={k} title={s.detail}><Pill>{SRC_LABEL[s.type] ?? s.type}</Pill></span>)}
                {m.reply.action?.type === "navigate" && <Link className="text-sm font-semibold text-leaf underline" to={m.reply.action.path} state={{ prefill: m.reply.action.prefill }}>Open</Link>}
                {m.reply.data?.analysis_id && m.reply.intent === "nutrition" && <Link className="text-sm font-semibold text-leaf underline" to={`/nutrition/${m.reply.data.analysis_id}`}>Details</Link>}
              </div>
            )}
          </div>
        ))}
        {send.isPending && <p className="text-sm text-muted" role="status">Thinking… a local model can take a little while.</p>}
        <ErrorNotice error={send.error} />
        {micError && <Notice tone="warn">{micError}</Notice>}
      </div>
      <form className="sticky bottom-0 mt-4 flex flex-wrap items-center gap-2 border-t border-line bg-paper py-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input aria-label="Message" className="min-w-0 flex-1 rounded-lg border border-line bg-white px-3 py-2.5 text-sm" placeholder="Ask about food…" maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} />
        <label className="cursor-pointer rounded-lg border border-line bg-card px-3 py-2.5 text-sm font-semibold hover:bg-leaf-soft has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-leaf">
          {image ? `📎 ${image.name.slice(0, 12)}` : "Attach photo"}<input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => setImage(e.target.files?.[0] ?? null)} />
        </label>
        <Button type="button" variant={recording ? "danger" : "secondary"} aria-pressed={recording} onClick={toggleMic}>{recording ? "Stop & send" : "Speak"}</Button>
        <Button type="submit" loading={send.isPending} disabled={!text.trim() && !image}>Send</Button>
      </form>
    </>
  );
}
