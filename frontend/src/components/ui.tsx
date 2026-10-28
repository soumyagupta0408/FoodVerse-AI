import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import { ApiError, mediaBlob } from "../lib/api";

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : "Something went wrong";
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; loading?: boolean };
export function Button({ variant = "primary", loading, className = "", children, disabled, ...rest }: BtnProps) {
  const styles = {
    primary: "bg-leaf text-white hover:bg-leaf-dark",
    secondary: "bg-card text-ink border border-line hover:bg-leaf-soft",
    danger: "bg-berry text-white hover:opacity-90",
    ghost: "text-leaf hover:bg-leaf-soft",
  }[variant];
  return (
    <button {...rest} disabled={disabled || loading} aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}>
      {loading && <Spinner small />}
      {children}
    </button>
  );
}

export function Spinner({ small }: { small?: boolean }) {
  const s = small ? "h-4 w-4" : "h-6 w-6";
  return <span role="status" aria-label="Loading" className={`inline-block ${s} animate-spin rounded-full border-2 border-current border-t-transparent`} />;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-line bg-card p-5 ${className}`}>{children}</section>;
}

export function PageHeader({ title, intro, actions }: { title: string; intro?: string; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold">{title}</h1>
        {intro && <p className="mt-1 text-muted">{intro}</p>}
      </div>
      {actions}
    </header>
  );
}

export const inputCls = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm placeholder:text-muted/70 focus:border-leaf";

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: (id: string, describedBy: string | undefined) => ReactNode }) {
  const id = useId();
  const desc = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">{label}</label>
      {children(id, desc)}
      {hint && !error && <p id={`${id}-hint`} className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p id={`${id}-err`} role="alert" className="mt-1 text-xs text-berry">{error}</p>}
    </div>
  );
}

export function TextInput({ label, error, hint, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: string }) {
  return <Field label={label} error={error} hint={hint}>{(id, d) => <input id={id} aria-describedby={d} aria-invalid={!!error} className={inputCls} {...rest} />}</Field>;
}

const tones = {
  good: "bg-leaf-soft text-leaf-dark", warn: "bg-amber-soft text-amber", bad: "bg-berry-soft text-berry", neutral: "bg-sky-soft text-ink",
};
export type Tone = keyof typeof tones;
export function Pill({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function Notice({ tone = "neutral", title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  const role = tone === "bad" ? "alert" : "status";
  return (
    <div role={role} className={`rounded-lg px-4 py-3 text-sm ${tones[tone]}`}>
      {title && <p className="font-semibold">{title}</p>}
      <div>{children}</div>
    </div>
  );
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as ApiError;
  const extra = Array.isArray(e.details) ? e.details.filter((d: any) => d?.msg).map((d: any) => d.msg).join("; ") : "";
  return <Notice tone="bad" title={errorMessage(error)}>{extra || (e.requestId ? `Reference: ${e.requestId}` : "")}</Notice>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line px-6 py-10 text-center">
      <p className="font-display text-lg font-semibold">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

/** Confidence is shown as a number AND a bar, never colour alone. */
export function ConfidenceBar({ value, label }: { value: number | null | undefined; label?: string }) {
  if (value == null) return <span className="text-sm text-muted">Confidence unavailable</span>;
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="flex justify-between text-xs"><span>{label ?? "Confidence"}</span><span className="font-semibold">{pct}%</span></div>
      <div className="mt-1 h-2 rounded-full bg-line" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label ?? "Confidence"}>
        <div className="h-2 rounded-full bg-leaf" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function Limits({ title = "What this can't tell you", children }: { title?: string; children: ReactNode }) {
  return (
    <aside className="rounded-lg border-l-4 border-amber bg-amber-soft px-4 py-3 text-sm">
      <p className="font-semibold text-amber">{title}</p>
      <div className="mt-0.5">{children}</div>
    </aside>
  );
}

export function FileDrop({ accept, onFile, file, hint, kind }: { accept: string; onFile: (f: File | null) => void; file: File | null; hint: string; kind: "image" | "video" | "audio" }) {
  const id = useId();
  const [url, setUrl] = useState<string | null>(null);
  const pick = (f: File | null) => {
    if (url) URL.revokeObjectURL(url);
    setUrl(f && kind !== "audio" ? URL.createObjectURL(f) : null);
    onFile(f);
  };
  return (
    <div>
      <label htmlFor={id} className="flex cursor-pointer flex-col items-center gap-1 rounded-xl border-2 border-dashed border-line bg-white px-6 py-8 text-center hover:border-leaf has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-leaf">
        <span className="font-semibold">{file ? file.name : `Choose a ${kind} file`}</span>
        <span className="text-xs text-muted">{hint}</span>
        <input id={id} type="file" accept={accept} className="sr-only" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
      </label>
      {url && kind === "image" && <img src={url} alt="Selected upload preview" className="mt-3 max-h-64 rounded-lg border border-line object-contain" />}
      {url && kind === "video" && <video src={url} controls className="mt-3 max-h-64 rounded-lg border border-line" />}
    </div>
  );
}

export function AuthedImage({ mediaId, alt, className = "" }: { mediaId: string; alt: string; className?: string }) {
  const q = useQuery({ queryKey: ["media", mediaId], queryFn: () => mediaBlob(mediaId), staleTime: Infinity, gcTime: 5 * 60_000 });
  if (q.isPending) return <div className={`animate-pulse rounded-lg bg-line ${className}`} style={{ minHeight: 120 }} aria-label="Loading image" />;
  if (q.isError) return <p className="text-sm text-muted">Image unavailable (it may have passed its retention period).</p>;
  return <img src={q.data} alt={alt} className={`rounded-lg border border-line ${className}`} />;
}

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
      {items.map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="font-medium">{v}</dd></div>))}
    </dl>
  );
}

export const fmtDate = (s: string) => new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
