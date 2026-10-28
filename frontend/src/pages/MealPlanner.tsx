import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation } from "react-router-dom";
import { z } from "zod";
import { Button, Card, ErrorNotice, Limits, Notice, PageHeader, Pill, Spinner, TextInput, inputCls } from "../components/ui";
import { api } from "../lib/api";
import { splitList } from "../lib/util";
import type { MealPlan } from "../lib/types";

const schema = z.object({
  days: z.string().refine((v) => Number(v) >= 1 && Number(v) <= 7, "1 to 7 days"), servings: z.string().refine((v) => Number(v) >= 1 && Number(v) <= 12, "1 to 12"),
  meals: z.array(z.string()).min(1, "Pick at least one meal"), diet_pattern: z.string(), allergies: z.string().max(300), excluded: z.string().max(300), cuisines: z.string().max(200),
  available: z.string().max(500), kcal: z.string().refine((v) => v === "" || (Number(v) >= 800 && Number(v) <= 6000), "800 to 6000 kcal"),
});
type Form = z.infer<typeof schema>;
const MEALS = ["breakfast", "lunch", "dinner", "snack"];

function PlanView({ plan }: { plan: MealPlan }) {
  const qc = useQueryClient();
  const [day, setDay] = useState(1);
  const [instr, setInstr] = useState("");
  const refresh = (p: MealPlan) => qc.setQueryData(["plan", plan.id], p);
  const replace = useMutation({ mutationFn: (mt: string) => api<MealPlan>(`/meal-plans/${plan.id}`, { method: "PATCH", json: { replace: { day, meal_type: mt, instruction: instr || null } } }), onSuccess: refresh });
  const rate = useMutation({ mutationFn: (v: { mt: string; rating: number }) => api<MealPlan>(`/meal-plans/${plan.id}`, { method: "PATCH", json: { feedback: { day, meal_type: v.mt, rating: v.rating } } }), onSuccess: refresh });
  const shop = useMutation({ mutationFn: () => api<{ items: any[]; note: string }>(`/meal-plans/${plan.id}/shopping-list`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["plan", plan.id] }) });
  const days: any[] = plan.plan.days;
  const cur = days.find((d) => d.day === day) ?? days[0];
  const list = plan.shopping_list ?? shop.data?.items;

  return (
    <div className="space-y-4">
      <Card>
        <div role="tablist" aria-label="Days" className="mb-4 flex flex-wrap gap-1">
          {days.map((d) => <button key={d.day} role="tab" aria-selected={d.day === day} className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${d.day === day ? "bg-leaf text-white" : "bg-paper hover:bg-leaf-soft"}`} onClick={() => setDay(d.day)}>Day {d.day}</button>)}
        </div>
        <p className="mb-3 text-sm text-muted">{cur.daily_nutrition.kcal_matched} kcal estimated{plan.plan.target_kcal_per_day ? ` (your goal: ${plan.plan.target_kcal_per_day})` : ""}. {cur.daily_nutrition.note}</p>
        <ul className="space-y-3">
          {cur.meals.map((m: any) => (
            <li key={m.meal_type} className="rounded-lg border border-line p-4">
              <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold"><span className="capitalize text-muted">{m.meal_type}:</span> {m.title}</h3><Pill>AI suggestion</Pill></div>
              {m.description && <p className="text-sm text-muted">{m.description}</p>}
              <p className="mt-1 text-sm">{m.ingredients.map((i: any) => `${i.name} ${i.grams} g`).join(" · ")}</p>
              <p className="mt-1 text-xs text-muted">≈ {m.nutrition_estimate.totals.kcal ?? "?"} kcal per serving ({m.nutrition_estimate.complete ? "all ingredients matched" : `${m.nutrition_estimate.unmatched_ingredients.length} unmatched, so a lower bound`})</p>
              {m.rationale && <p className="mt-1 text-sm"><em>Why:</em> {m.rationale}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button variant="secondary" loading={replace.isPending && replace.variables === m.meal_type} onClick={() => replace.mutate(m.meal_type)}>Replace</Button>
                <span className="text-xs text-muted">Rate:</span>
                {[1, 2, 3, 4, 5].map((n) => <button key={n} aria-label={`Rate ${n} out of 5`} className="rounded px-1.5 text-sm hover:bg-leaf-soft" onClick={() => rate.mutate({ mt: m.meal_type, rating: n })}>{n}</button>)}
              </div>
            </li>
          ))}
        </ul>
        <div className="mt-3 max-w-md"><TextInput label="Instruction for a replacement (optional)" value={instr} onChange={(e) => setInstr(e.target.value)} maxLength={300} placeholder="lighter, no rice…" /></div>
        <div className="mt-3"><ErrorNotice error={replace.error ?? rate.error} /></div>
      </Card>
      <Card>
        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">Shopping list</h2><Button variant="secondary" loading={shop.isPending} onClick={() => shop.mutate()}>{list ? "Rebuild" : "Create shopping list"}</Button></div>
        <ErrorNotice error={shop.error} />
        {list && (
          <table className="mt-3 w-full text-sm"><caption className="sr-only">Shopping list</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">Item</th><th>Total</th><th>Have it?</th></tr></thead>
            <tbody>{list.map((i: any) => <tr key={i.name} className="border-t border-line"><td className="py-1.5">{i.name}</td><td>{i.total_grams} g</td><td>{i.have_at_home ? "Yes" : ""}</td></tr>)}</tbody></table>
        )}
        {list && <p className="mt-2 text-xs text-muted">Totals add up the generated gram weights across all meals and servings. Round up to package sizes.</p>}
      </Card>
      <Limits title="Please note">{plan.plan.notes?.join(" ")} {plan.plan.caveat}</Limits>
    </div>
  );
}

export default function MealPlanner() {
  const loc = useLocation();
  const pre = (loc.state as any)?.prefill as { days?: number } | undefined;
  const [planId, setPlanId] = useState<string | null>(null);
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { days: String(pre?.days ?? 1), servings: "1", meals: ["breakfast", "lunch", "dinner"], diet_pattern: "", allergies: "", excluded: "", cuisines: "", available: "", kcal: "" } });
  const start = useMutation({
    mutationFn: (v: Form) => api<MealPlan>("/meal-plans/generate", { json: { days: Number(v.days), servings: Number(v.servings), meals: v.meals, diet_pattern: v.diet_pattern || null, allergies: splitList(v.allergies),
      excluded_ingredients: splitList(v.excluded), cuisines: splitList(v.cuisines), available_ingredients: splitList(v.available), target_kcal_per_day: v.kcal ? Number(v.kcal) : null } }),
    onSuccess: (p) => setPlanId(p.id),
  });
  const plan = useQuery({ queryKey: ["plan", planId], queryFn: () => api<MealPlan>(`/meal-plans/${planId}`), enabled: !!planId,
    refetchInterval: (q) => (q.state.data?.status === "generating" ? 3000 : false) });
  const e = f.formState.errors;

  return (
    <>
      <PageHeader title="Meal Planner" intro="Build a daily or weekly plan. Every meal is checked in code against your allergies and diet before you see it." />
      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        <Card>
          <form onSubmit={f.handleSubmit((v) => start.mutate(v))} className="space-y-3" noValidate>
            <div className="grid grid-cols-2 gap-3"><TextInput label="Days" type="number" error={e.days?.message} {...f.register("days")} /><TextInput label="Servings per meal" type="number" error={e.servings?.message} {...f.register("servings")} /></div>
            <fieldset><legend className="mb-1 text-sm font-medium">Meals</legend><div className="flex flex-wrap gap-3 text-sm">{MEALS.map((m) => <label key={m} className="flex items-center gap-1.5 capitalize"><input type="checkbox" value={m} {...f.register("meals")} />{m}</label>)}</div>{e.meals && <p role="alert" className="text-xs text-berry">{e.meals.message}</p>}</fieldset>
            <div><label htmlFor="dp" className="mb-1 block text-sm font-medium">Diet</label><select id="dp" className={inputCls} {...f.register("diet_pattern")}><option value="">Use my profile / none</option>{["omnivore", "vegetarian", "vegan", "pescatarian"].map((x) => <option key={x}>{x}</option>)}</select></div>
            <TextInput label="Allergies" hint="Comma separated" {...f.register("allergies")} />
            <TextInput label="Never include" {...f.register("excluded")} />
            <TextInput label="Cuisines" {...f.register("cuisines")} />
            <TextInput label="Ingredients you already have" {...f.register("available")} />
            <TextInput label="Daily calorie goal (optional)" type="number" hint="Your own target, not medical advice." error={e.kcal?.message} {...f.register("kcal")} />
            <Button type="submit" className="w-full" loading={start.isPending}>Generate plan</Button>
            <ErrorNotice error={start.error} />
          </form>
        </Card>
        <div>
          {!planId && <Notice>Plans are generated by a local model, so a week can take several minutes. You can leave this page open and watch the status.</Notice>}
          {plan.isPending && planId && <Spinner />}
          {plan.data?.status === "generating" && <Notice tone="warn" title="Generating your plan…">Meals are created and safety-checked one day at a time.</Notice>}
          {plan.data?.status === "failed" && <Notice tone="bad" title="The plan could not be completed">{plan.data.error}</Notice>}
          {plan.data?.status === "ready" && <PlanView plan={plan.data} />}
          <ErrorNotice error={plan.error} />
        </div>
      </div>
    </>
  );
}
