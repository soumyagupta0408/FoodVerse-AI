import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AuthedImage, Button, Card, ConfidenceBar, ErrorNotice, FileDrop, Limits, Notice, PageHeader, Pill, TextInput } from "../components/ui";
import { api } from "../lib/api";
import type { Analysis } from "../lib/types";

const TONE: Record<string, "good" | "warn" | "bad" | "neutral"> = { fresh: "good", moderate: "warn", spoiled: "bad", unable_to_determine: "neutral" };

export default function Freshness() {
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState("");
  const cats = useQuery({ queryKey: ["fresh-cats"], queryFn: () => api<{ categories: string[] }>("/freshness/categories") });
  const run = useMutation({ mutationFn: () => { const f = new FormData(); f.append("file", file!); if (category.trim()) f.append("food_category", category.trim()); return api<Analysis>("/freshness/analyze", { form: f }); } });
  const r = run.data?.result;
  const supported = cats.data?.categories ?? [];

  return (
    <>
      <PageHeader title="Freshness Checker" intro="A visual freshness estimate for specific foods. It looks at appearance only." />
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          {cats.isSuccess && supported.length === 0 && <div className="mb-4"><Notice tone="warn" title="No freshness models installed">Freshness checks need a model trained for each food. See docs/MODELS.md to train one. Until then every result will be “Unable to determine”.</Notice></div>}
          <div className="space-y-4">
            <div>
              <TextInput label="Food type" list="fresh-cats" value={category} onChange={(e) => setCategory(e.target.value)} hint={supported.length ? `Supported: ${supported.join(", ")}` : "e.g. banana"} />
              <datalist id="fresh-cats">{supported.map((c) => <option key={c} value={c} />)}</datalist>
            </div>
            <FileDrop kind="image" accept="image/jpeg,image/png,image/webp" file={file} onFile={setFile} hint="A close, well-lit photo works best" />
            <Button className="w-full" disabled={!file} loading={run.isPending} onClick={() => run.mutate()}>Check freshness</Button>
            <ErrorNotice error={run.error} />
          </div>
        </Card>
        <div className="space-y-4">
          {!r && <Notice>The result will appear here, together with what it can and cannot tell you.</Notice>}
          {r && (
            <Card>
              <div className="flex items-center gap-3"><h2 className="text-2xl font-semibold">{r.display}</h2><Pill tone={TONE[r.state] ?? "neutral"}>{r.state === "unable_to_determine" ? "Not a verdict" : "Visual estimate"}</Pill></div>
              {run.data?.media_id && <div className="mt-3"><AuthedImage mediaId={run.data.media_id} alt="Photo you submitted" className="max-h-48" /></div>}
              <div className="mt-3">{r.state !== "unable_to_determine" ? <ConfidenceBar value={r.confidence} /> : <p className="text-sm">{r.reason}</p>}</div>
              {r.indicators?.map((i: string) => <p key={i} className="mt-2 text-sm text-muted">{i}</p>)}
              <p className="mt-3 text-sm"><strong>Suggestion:</strong> {r.recommendation}</p>
              {r.quality?.issues?.length > 0 && <p className="mt-2 text-sm text-amber">Photo quality: {r.quality.issues.join(", ")}.</p>}
            </Card>
          )}
          <Limits title="Visual checks are not a safety test">{r?.safety_note ?? "Looking fresh does not mean food is safe. Photos cannot show bacteria or toxins: consider storage temperature, storage time, and the expiry date."}</Limits>
        </div>
      </div>
    </>
  );
}
