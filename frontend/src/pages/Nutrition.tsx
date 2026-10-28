import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { z } from "zod";
import { Button, Card, ErrorNotice, KeyValue, Limits, Notice, PageHeader, Pill, Spinner, TextInput } from "../components/ui";
import { api, exportText } from "../lib/api";
import type { Analysis } from "../lib/types";

const schema = z.object({
  food_name: z.string().min(1, "Enter a food").max(200),
  grams: z.string().refine((v) => v === "" || (Number(v) > 0 && Number(v) <= 5000), "Enter 1 to 5000 grams, or leave blank for the default serving"),
});
type Form = z.infer<typeof schema>;
const NUT: [string, string, string][] = [["kcal", "Energy", "kcal"], ["protein_g", "Protein", "g"], ["carbs_g", "Carbohydrates", "g"], ["fat_g", "Total fat", "g"], ["fiber_g", "Fibre", "g"], ["sugar_g", "Sugar", "g"]];

export default function Nutrition() {
  const { id } = useParams();
  const loc = useLocation();
  const nav = useNavigate();
  const incoming = loc.state as { recognitionId?: string; foodName?: string } | null;
  const [result, setResult] = useState<Analysis | null>(null);
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { food_name: incoming?.foodName ?? "", grams: "" } });

  const loaded = useQuery({ queryKey: ["nutrition", id], queryFn: () => api<Analysis>(`/nutrition/${id}`), enabled: !!id });
  useEffect(() => { if (loaded.data) setResult(loaded.data); }, [loaded.data]);

  const run = useMutation({
    mutationFn: (v: Form) => api<Analysis>("/nutrition/analyze", { json: { food_name: v.food_name, grams: v.grams ? Number(v.grams) : null, recognition_id: incoming?.recognitionId ?? null } }),
    onSuccess: (a) => { setResult(a); nav(`/nutrition/${a.id}`, { replace: true }); },
  });
  const r = result?.result;
  const exp = useMutation({ mutationFn: () => exportText(`/exports/analysis/${result!.id}?format=md`), onSuccess: (t) => {
    const url = URL.createObjectURL(new Blob([t], { type: "text/markdown" })); const a = document.createElement("a"); a.href = url; a.download = `nutrition-${result!.id}.md`; a.click(); URL.revokeObjectURL(url);
  } });

  return (
    <>
      <PageHeader title="Nutrition Analyzer" intro="Values are scaled from per-100 g database records. Unknown nutrients are shown as unknown, never as zero." />
      <div className="grid gap-6 md:grid-cols-[20rem_1fr]">
        <Card>
          <form onSubmit={f.handleSubmit((v) => run.mutate(v))} className="space-y-4" noValidate>
            <TextInput label="Food or dish" error={f.formState.errors.food_name?.message} {...f.register("food_name")} />
            <TextInput label="Portion in grams" inputMode="decimal" hint="Leave blank to use the default serving (marked as an estimate)." error={f.formState.errors.grams?.message} {...f.register("grams")} />
            <Button type="submit" className="w-full" loading={run.isPending}>Analyse</Button>
            <ErrorNotice error={run.error} />
          </form>
        </Card>
        <div className="space-y-4">
          {id && loaded.isPending && <Spinner />}
          {loaded.isError && <ErrorNotice error={loaded.error} />}
          {!result && !id && <Notice>Enter a food to see calories, protein, carbohydrates and fat for a chosen portion.</Notice>}
          {r && !r.matched && <Notice tone="warn" title="No nutrition record found">{r.message}</Notice>}
          {r?.matched && (
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-2xl font-semibold capitalize">{r.food.name}</h2>
                <Pill tone={r.portion.estimated ? "warn" : "good"}>{r.portion.grams} g{r.portion.estimated ? " · estimated portion" : ""}</Pill>
              </div>
              {r.match_note && <p className="mt-1 text-sm text-amber">{r.match_note}</p>}
              <div className="mt-4 grid gap-6 sm:grid-cols-2">
                <dl className="space-y-2">
                  {NUT.map(([k, label, unit]) => (
                    <div key={k} className="flex justify-between border-b border-line pb-1 text-sm">
                      <dt>{label}</dt><dd className="font-semibold">{r.nutrients[k] == null ? <span className="font-normal text-muted">unknown</span> : `${r.nutrients[k]} ${unit}`}</dd>
                    </div>
                  ))}
                </dl>
                <div className="h-44" role="img" aria-label="Share of energy-providing macronutrients by weight">
                  <ResponsiveContainer><PieChart><Pie dataKey="v" nameKey="n" innerRadius={35} outerRadius={65} data={[{ n: "Protein", v: r.nutrients.protein_g ?? 0 }, { n: "Carbs", v: r.nutrients.carbs_g ?? 0 }, { n: "Fat", v: r.nutrients.fat_g ?? 0 }]}>
                    {["#2f6b4f", "#9a6410", "#6b8fa3"].map((c) => <Cell key={c} fill={c} />)}</Pie><Tooltip formatter={(v) => `${v} g`} /></PieChart></ResponsiveContainer>
                </div>
              </div>
              <div className="mt-4 rounded-lg bg-paper p-3 text-sm">
                <p><strong>Health score: {r.health_score.score}/100</strong> <span className="text-muted">(a rough heuristic, not medical advice)</span></p>
                <ul className="mt-1 text-xs text-muted">
                  {r.health_score.components.map((c: any) => <li key={c.criterion}>{c.criterion}: {c.points > 0 ? "+" : ""}{c.points}</li>)}
                  {r.health_score.skipped.length > 0 && <li>Skipped (unknown): {r.health_score.skipped.join(", ")}</li>}
                </ul>
                <details className="mt-1 text-xs text-muted"><summary className="cursor-pointer">How it is calculated</summary>{r.health_score.criteria}</details>
              </div>
              <div className="mt-4"><KeyValue items={[["Source", r.food.source], ["Verified data", r.food.verified ? "Yes" : "No: demo or unverified"], ["Name match", `${Math.round((r.match_score ?? 0) * 100)}%`]]} /></div>
              <Button variant="secondary" className="mt-4" onClick={() => exp.mutate()} loading={exp.isPending}>Export report (Markdown)</Button>
            </Card>
          )}
          {r?.matched && r.notes.length > 0 && <Limits>{r.notes.join(" ")}</Limits>}
        </div>
      </div>
    </>
  );
}
