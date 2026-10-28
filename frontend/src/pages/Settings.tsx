import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button, Card, ErrorNotice, Notice, PageHeader, TextInput, inputCls } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { joinList, splitList } from "../lib/util";

const schema = z.object({ display_name: z.string().max(100), diet_pattern: z.string(), allergies: z.string().max(300), excluded: z.string().max(500), cuisines: z.string().max(300) });
type Form = z.infer<typeof schema>;

export default function Settings() {
  const { user, reload, signOut } = useAuth();
  const nav = useNavigate();
  const p = user?.profile;
  const [saved, setSaved] = useState(false);
  const [confirm, setConfirm] = useState("");
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { display_name: p?.display_name ?? "", diet_pattern: p?.diet_pattern ?? "", allergies: joinList(p?.allergies), excluded: joinList(p?.excluded_ingredients), cuisines: joinList(p?.cuisines) } });
  const save = useMutation({
    mutationFn: (v: Form) => api("/users/me/profile", { method: "PATCH", json: { display_name: v.display_name || null, diet_pattern: v.diet_pattern || null, allergies: splitList(v.allergies), excluded_ingredients: splitList(v.excluded), cuisines: splitList(v.cuisines) } }),
    onSuccess: async () => { await reload(); setSaved(true); },
  });
  const del = useMutation({ mutationFn: () => api<void>("/users/me", { method: "DELETE" }), onSuccess: async () => { await signOut(); nav("/login"); } });

  return (
    <>
      <PageHeader title="Profile & Settings" intro="These preferences are applied automatically to recipes and meal plans." />
      <div className="max-w-xl space-y-6">
        <Card>
          <form className="space-y-4" onSubmit={f.handleSubmit((v) => { setSaved(false); save.mutate(v); })}>
            <TextInput label="Display name" {...f.register("display_name")} />
            <div><label htmlFor="dp" className="mb-1 block text-sm font-medium">Dietary pattern</label><select id="dp" className={inputCls} {...f.register("diet_pattern")}><option value="">No preference</option>{["omnivore", "vegetarian", "vegan", "pescatarian"].map((x) => <option key={x}>{x}</option>)}</select></div>
            <TextInput label="Allergies" hint="Comma separated, e.g. peanut, milk, shellfish. Always enforced in code." {...f.register("allergies")} />
            <TextInput label="Ingredients to avoid" {...f.register("excluded")} />
            <TextInput label="Favourite cuisines" {...f.register("cuisines")} />
            <Button type="submit" loading={save.isPending}>Save preferences</Button>
            {saved && <Notice tone="good">Preferences saved.</Notice>}
            <ErrorNotice error={save.error} />
          </form>
        </Card>
        <Card>
          <h2 className="text-lg font-semibold">Delete account</h2>
          <p className="mb-3 text-sm text-muted">Permanently removes your account, history, reports and all stored photos and videos. This cannot be undone.</p>
          <TextInput label={`Type ${user?.email} to confirm`} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <Button variant="danger" className="mt-3" disabled={confirm !== user?.email} loading={del.isPending} onClick={() => del.mutate()}>Delete everything</Button>
          <ErrorNotice error={del.error} />
        </Card>
      </div>
    </>
  );
}
