import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, Card, Empty, ErrorNotice, Limits, Notice, PageHeader, Pill, Spinner, TextInput, inputCls } from "../components/ui";
import { api } from "../lib/api";
import { splitList } from "../lib/util";
import type { Page, Recipe } from "../lib/types";

const schema = z.object({
  ingredients: z.string().max(600), cuisine: z.string().max(60), meal_type: z.string(), cooking_minutes: z.string().refine((v) => v === "" || (Number(v) >= 5 && Number(v) <= 480), "5 to 480 minutes"),
  skill_level: z.string(), servings: z.string().refine((v) => Number(v) >= 1 && Number(v) <= 24, "1 to 24"), allergies: z.string().max(300), excluded: z.string().max(300),
  equipment: z.string().max(300), notes: z.string().max(300),
});
type Form = z.infer<typeof schema>;

function RecipeView({ r, onChange }: { r: Recipe; onChange: (r: Recipe) => void }) {
  const qc = useQueryClient();
  const d = r.data, m = r.meta;
  const [servings, setServings] = useState(String(d.servings));
  const [tweak, setTweak] = useState("");
  const [sub, setSub] = useState({ ingredient: d.ingredients[0]?.name ?? "", replacement: "" });
  const [alts, setAlts] = useState<any[] | null>(null);
  const done = (x: Recipe) => { onChange(x); qc.invalidateQueries({ queryKey: ["recipes"] }); setAlts(null); };

  const save = useMutation({ mutationFn: () => api<Recipe>(`/recipes/${r.id}/save`, { json: { saved: !r.saved } }), onSuccess: done });
  const scale = useMutation({ mutationFn: () => api<Recipe>(`/recipes/${r.id}/scale`, { json: { servings: Number(servings) } }), onSuccess: done });
  const revise = useMutation({ mutationFn: () => api<Recipe>(`/recipes/${r.id}/revise`, { json: { request: tweak, servings: Number(servings) || d.servings } }), onSuccess: (x) => { done(x); setTweak(""); } });
  const subst = useMutation({ mutationFn: () => api<any>(`/recipes/${r.id}/substitute`, { json: { ingredient: sub.ingredient, replacement: sub.replacement || null } }),
    onSuccess: (res) => (res.applied ? done(res.recipe) : setAlts(res.alternatives)) });
  const err = save.error ?? scale.error ?? revise.error ?? subst.error;
  const est = m.nutrition_estimate;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><h2 className="text-2xl font-semibold">{r.title}</h2><p className="text-sm text-muted">{d.description}</p></div>
        <Button variant={r.saved ? "secondary" : "primary"} loading={save.isPending} onClick={() => save.mutate()}>{r.saved ? "Saved ✓ (remove)" : "Save recipe"}</Button>
      </div>
      <p className="mt-2 text-sm">Serves {d.servings} · prep {d.prep_minutes} min · cook {d.cook_minutes} min</p>
      <div className="mt-4 grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="mb-1 font-semibold">Ingredients</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-sm">{d.ingredients.map((i: any, k: number) => <li key={k}>{i.quantity != null ? `${i.quantity} ${i.unit ?? ""} ` : ""}{i.name}{i.grams ? <span className="text-muted"> (~{i.grams} g)</span> : null}</li>)}</ul>
        </div>
        <div>
          <h3 className="mb-1 font-semibold">Steps</h3>
          <ol className="list-decimal space-y-1 pl-5 text-sm">{d.steps.map((s: string, k: number) => <li key={k}>{s}</li>)}</ol>
        </div>
      </div>
      {d.tips?.length > 0 && <div className="mt-3 text-sm"><h3 className="font-semibold">Tips</h3><ul className="list-disc pl-5">{d.tips.map((t: string) => <li key={t}>{t}</li>)}</ul></div>}
      {d.food_safety?.length > 0 && <div className="mt-3"><Limits title="Food safety">{d.food_safety.join(" ")}</Limits></div>}
      {est && (
        <div className="mt-3 rounded-lg bg-paper p-3 text-sm">
          <p className="font-semibold">Estimated nutrition for the whole recipe <Pill tone={est.complete ? "good" : "warn"}>{est.complete ? "all ingredients matched" : "partial"}</Pill></p>
          <p>{est.totals.kcal ?? "unknown"} kcal · protein {est.totals.protein_g ?? "?"} g · carbs {est.totals.carbs_g ?? "?"} g · fat {est.totals.fat_g ?? "?"} g</p>
          <p className="text-xs text-muted">{est.note} {est.unmatched_ingredients.length > 0 && `Not matched: ${est.unmatched_ingredients.join(", ")}.`}</p>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">{m.provenance?.note} {m.restriction_check?.applied?.length ? `Restrictions checked: ${m.restriction_check.applied.join(", ")}. ` : ""}{m.restriction_check?.caveat}</p>

      <div className="mt-5 grid gap-4 border-t border-line pt-4 md:grid-cols-2">
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); scale.mutate(); }}>
          <div className="flex-1"><TextInput label="Change servings" type="number" min={1} max={48} value={servings} onChange={(e) => setServings(e.target.value)} /></div>
          <Button type="submit" variant="secondary" loading={scale.isPending}>Rescale</Button>
        </form>
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (tweak.trim()) revise.mutate(); }}>
          <div className="flex-1"><TextInput label="Ask for a change" placeholder="make it spicier, no oven…" value={tweak} onChange={(e) => setTweak(e.target.value)} maxLength={500} /></div>
          <Button type="submit" variant="secondary" loading={revise.isPending} disabled={!tweak.trim()}>Revise</Button>
        </form>
        <form className="md:col-span-2" onSubmit={(e) => { e.preventDefault(); subst.mutate(); }}>
          <p className="mb-1 text-sm font-medium">Swap an ingredient</p>
          <div className="flex flex-wrap items-end gap-2">
            <select aria-label="Ingredient to replace" className={`${inputCls} max-w-xs`} value={sub.ingredient} onChange={(e) => setSub({ ...sub, ingredient: e.target.value })}>{d.ingredients.map((i: any) => <option key={i.name}>{i.name}</option>)}</select>
            <input aria-label="Replacement (optional)" className={`${inputCls} max-w-xs`} placeholder="Replacement, or leave blank for ideas" value={sub.replacement} onChange={(e) => setSub({ ...sub, replacement: e.target.value })} />
            <Button type="submit" variant="secondary" loading={subst.isPending}>{sub.replacement ? "Apply swap" : "Suggest swaps"}</Button>
          </div>
        </form>
      </div>
      {alts && <ul className="mt-3 space-y-1 text-sm">{alts.map((a) => <li key={a.name}><Pill>AI idea</Pill> <strong>{a.name}</strong> {a.note}</li>)}</ul>}
      <div className="mt-3"><ErrorNotice error={err} /></div>
    </Card>
  );
}

export default function Cooking() {
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const saved = useQuery({ queryKey: ["recipes", "saved"], queryFn: () => api<Page<Recipe>>("/recipes?saved=true&page_size=20") });
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { ingredients: "", cuisine: "", meal_type: "", cooking_minutes: "", skill_level: "", servings: "2", allergies: "", excluded: "", equipment: "", notes: "" } });
  const gen = useMutation({
    mutationFn: (v: Form) => api<Recipe>("/recipes/generate", { json: {
      ingredients: splitList(v.ingredients), cuisine: v.cuisine || null, meal_type: v.meal_type || null, cooking_minutes: v.cooking_minutes ? Number(v.cooking_minutes) : null,
      skill_level: v.skill_level || null, servings: Number(v.servings), allergies: splitList(v.allergies), excluded_ingredients: splitList(v.excluded), equipment: splitList(v.equipment), dietary_notes: v.notes || null } }),
    onSuccess: setRecipe,
  });
  const e = f.formState.errors;

  return (
    <>
      <PageHeader title="Cooking Assistant" intro="Tell it what you have and any restrictions. Allergy and exclusion checks run in code on every recipe, not just in the prompt." />
      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        <Card>
          <form onSubmit={f.handleSubmit((v) => gen.mutate(v))} className="space-y-3" noValidate>
            <TextInput label="Ingredients on hand" placeholder="rice, tomatoes, onion" hint="Separate with commas" error={e.ingredients?.message} {...f.register("ingredients")} />
            <div className="grid grid-cols-2 gap-3">
              <TextInput label="Servings" type="number" error={e.servings?.message} {...f.register("servings")} />
              <TextInput label="Max minutes" type="number" error={e.cooking_minutes?.message} {...f.register("cooking_minutes")} />
            </div>
            <TextInput label="Cuisine" {...f.register("cuisine")} />
            <div className="grid grid-cols-2 gap-3">
              <div><label className="mb-1 block text-sm font-medium" htmlFor="mt">Meal</label><select id="mt" className={inputCls} {...f.register("meal_type")}><option value="">Any</option>{["breakfast", "lunch", "dinner", "snack", "dessert"].map((x) => <option key={x}>{x}</option>)}</select></div>
              <div><label className="mb-1 block text-sm font-medium" htmlFor="sk">Skill</label><select id="sk" className={inputCls} {...f.register("skill_level")}><option value="">Any</option>{["beginner", "intermediate", "advanced"].map((x) => <option key={x}>{x}</option>)}</select></div>
            </div>
            <TextInput label="Allergies" hint="e.g. peanut, milk, shellfish" {...f.register("allergies")} />
            <TextInput label="Never include" hint="e.g. mushroom, coriander" {...f.register("excluded")} />
            <TextInput label="Equipment" placeholder="stovetop, microwave" {...f.register("equipment")} />
            <TextInput label="Other notes" {...f.register("notes")} />
            <Button type="submit" className="w-full" loading={gen.isPending}>Create recipe</Button>
            {gen.isPending && <p className="text-xs text-muted">A local model can take a minute or two on CPU.</p>}
            <ErrorNotice error={gen.error} />
          </form>
        </Card>
        <div className="space-y-4">
          {recipe ? <RecipeView key={recipe.id} r={recipe} onChange={setRecipe} /> : <Notice>Your recipe appears here. Saved restrictions from your profile are applied automatically.</Notice>}
          <Card>
            <h2 className="mb-2 text-lg font-semibold">Saved recipes</h2>
            {saved.isPending ? <Spinner small /> : saved.data?.items.length ? (
              <ul className="divide-y divide-line text-sm">{saved.data.items.map((s) => <li key={s.id}><button className="w-full py-2 text-left font-medium text-leaf hover:underline" onClick={() => setRecipe(s)}>{s.title}</button></li>)}</ul>
            ) : <Empty title="No saved recipes">Save a recipe to keep it here.</Empty>}
          </Card>
        </div>
      </div>
    </>
  );
}
