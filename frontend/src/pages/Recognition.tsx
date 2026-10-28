import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthedImage, Button, Card, ConfidenceBar, ErrorNotice, FileDrop, fmtDate, Limits, Notice, PageHeader, TextInput } from "../components/ui";
import { api } from "../lib/api";
import type { Analysis } from "../lib/types";

export default function Recognition() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Analysis | null>(null);
  const [fix, setFix] = useState("");
  const nav = useNavigate();

  const run = useMutation({
    mutationFn: () => { const f = new FormData(); f.append("file", file!); return api<Analysis>("/food/recognize", { form: f }); },
    onSuccess: (a) => { setResult(a); setFix(""); },
  });
  const correct = useMutation({
    mutationFn: () => api<Analysis>(`/food/recognize/${result!.id}/correction`, { method: "PATCH", json: { food_name: fix.trim() } }),
    onSuccess: (a) => { setResult(a); setFix(""); },
  });
  const preds: { label: string; confidence: number }[] = result?.result.predictions ?? [];
  const chosen = result?.corrected?.food_name ?? result?.result.top?.label;

  return (
    <>
      <PageHeader title="Food Recognition" intro="Upload a photo of a dish. The model suggests what it is; you stay in control and can correct it." />
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <FileDrop kind="image" accept="image/jpeg,image/png,image/webp" file={file} onFile={(f) => { setFile(f); setResult(null); }} hint="JPEG, PNG or WEBP, up to 10 MB" />
          <Button className="mt-4 w-full" disabled={!file} loading={run.isPending} onClick={() => run.mutate()}>Identify food</Button>
          <div className="mt-3"><ErrorNotice error={run.error} /></div>
        </Card>
        <div className="space-y-4">
          {!result && !run.isPending && <Notice>Results appear here. One photo is treated as one dish: photos with several foods are not split apart.</Notice>}
          {result && (
            <Card>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs text-muted">Best guess</p>
                  <h2 className="text-2xl font-semibold capitalize">{chosen ?? "No prediction"}</h2>
                  {result.corrected && <p className="text-xs text-muted">Corrected by you (model said {result.result.top?.label}).</p>}
                </div>
                <time className="text-xs text-muted" dateTime={result.created_at}>{fmtDate(result.created_at)}</time>
              </div>
              {result.media_id && <div className="mt-3"><AuthedImage mediaId={result.media_id} alt="Your uploaded food" className="max-h-56" /></div>}
              <h3 className="mb-2 mt-4 text-sm font-semibold">Other possibilities</h3>
              <ul className="space-y-2">{preds.map((p) => <li key={p.label}><ConfidenceBar value={p.confidence} label={p.label} /></li>)}</ul>
              {result.result.notes?.map((n: string) => <p key={n} className="mt-3 text-sm text-muted">{n}</p>)}
              <form className="mt-4 flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (fix.trim()) correct.mutate(); }}>
                <div className="flex-1"><TextInput label="Not right? Enter the correct food" value={fix} onChange={(e) => setFix(e.target.value)} maxLength={200} /></div>
                <Button type="submit" variant="secondary" loading={correct.isPending} disabled={!fix.trim()}>Correct</Button>
              </form>
              <ErrorNotice error={correct.error} />
              <div className="mt-4 flex flex-wrap gap-2">
                <Button onClick={() => nav("/nutrition", { state: { recognitionId: result.id, foodName: chosen } })}>Analyse nutrition</Button>
                <Link to="/freshness" className="inline-flex items-center rounded-lg border border-line px-4 py-2.5 text-sm font-semibold hover:bg-leaf-soft">Check freshness</Link>
              </div>
              <p className="mt-3 text-xs text-muted">Model: {result.model_name}</p>
            </Card>
          )}
          {result && <Limits>A prediction is a statistical guess from one photo and can be wrong, especially for regional dishes the model was not trained on.</Limits>}
        </div>
      </div>
    </>
  );
}
