import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, Empty, ErrorNotice, fmtDate, Notice, PageHeader, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

interface Summary {
  counts: Record<string, number>; freshness_last_30d: Record<string, number>; nutrition_trend_30d: { date: string; food: string; kcal: number }[];
  hygiene_job_status: Record<string, number>; alerts: { type: string; message: string }[];
}
interface Hist { items: { kind: string; id: string; title: string; created_at: string; status: string }[] }

const LABELS: Record<string, string> = { recognition: "Recognitions", nutrition: "Nutrition analyses", freshness: "Freshness checks", hygiene_jobs: "Hygiene videos", recipes: "Recipes", saved_recipes: "Saved recipes", meal_plans: "Meal plans" };
const PATH: Record<string, string> = { recognition: "/recognize", nutrition: "/nutrition", freshness: "/freshness", hygiene: "/hygiene", recipe: "/cooking", meal_plan: "/meal-planner" };

export default function Dashboard() {
  const { user } = useAuth();
  const s = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Summary>("/dashboard/summary") });
  const h = useQuery({ queryKey: ["history", "recent"], queryFn: () => api<Hist>("/history?page_size=6") });
  if (s.isPending) return <Spinner />;
  if (s.isError) return <ErrorNotice error={s.error} />;
  const d = s.data;
  const total = Object.values(d.counts).reduce((a, b) => a + b, 0);
  const fresh = Object.entries(d.freshness_last_30d).map(([name, count]) => ({ name, count }));

  return (
    <>
      <PageHeader title={`Welcome${user?.profile?.display_name ? `, ${user.profile.display_name}` : ""}`} intro="Everything below is counted from your own saved analyses." />
      {d.alerts.length > 0 && (
        <div className="mb-6 space-y-2">{d.alerts.map((a) => <Notice key={a.type} tone="warn" title="Needs your attention">{a.message}</Notice>)}</div>
      )}
      {total === 0 ? (
        <Empty title="Nothing analysed yet">Start with <Link className="font-semibold text-leaf underline" to="/recognize">a food photo</Link> or ask the <Link className="font-semibold text-leaf underline" to="/assistant">assistant</Link> a question.</Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <h2 className="mb-3 text-lg font-semibold">Your activity</h2>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              {Object.entries(d.counts).map(([k, v]) => (<div key={k}><dt className="text-muted">{LABELS[k] ?? k}</dt><dd className="text-2xl font-semibold">{v}</dd></div>))}
            </dl>
          </Card>
          <Card>
            <h2 className="mb-3 text-lg font-semibold">Recent</h2>
            {h.isPending ? <Spinner small /> : h.data?.items.length ? (
              <ul className="divide-y divide-line text-sm">
                {h.data.items.map((i) => (
                  <li key={`${i.kind}-${i.id}`} className="py-2">
                    <Link className="font-medium text-leaf hover:underline" to={i.kind === "nutrition" ? `/nutrition/${i.id}` : i.kind === "hygiene" ? `/hygiene/${i.id}` : PATH[i.kind]}>{i.title}</Link>
                    <span className="block text-xs text-muted">{i.kind.replace("_", " ")} · {fmtDate(i.created_at)}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No recent items.</p>}
          </Card>
          <Card>
            <h2 className="mb-1 text-lg font-semibold">Energy per analysed food (last 30 days)</h2>
            <p className="mb-3 text-xs text-muted">kcal for each nutrition analysis, at the portion you chose or the database default.</p>
            {d.nutrition_trend_30d.length ? (
              <div className="h-52" role="img" aria-label="Line chart of kilocalories per analysed food">
                <ResponsiveContainer><LineChart data={d.nutrition_trend_30d.map((t, i) => ({ ...t, n: i + 1 }))}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="n" /><YAxis /><Tooltip formatter={(v) => [`${v} kcal`, "Energy"]} labelFormatter={(_, p) => p?.[0]?.payload?.food ?? ""} /><Line dataKey="kcal" stroke="#2f6b4f" strokeWidth={2} dot /></LineChart></ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-muted">No nutrition analyses in the last 30 days.</p>}
          </Card>
          <Card>
            <h2 className="mb-3 text-lg font-semibold">Freshness results (last 30 days)</h2>
            {fresh.length ? (
              <div className="h-52" role="img" aria-label="Bar chart of freshness results">
                <ResponsiveContainer><BarChart data={fresh}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" fill="#2f6b4f" /></BarChart></ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-muted">No freshness checks in the last 30 days.</p>}
          </Card>
        </div>
      )}
    </>
  );
}
