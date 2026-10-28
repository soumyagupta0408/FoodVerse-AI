import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, Card, Empty, ErrorNotice, fmtDate, PageHeader, Pill, Spinner } from "../components/ui";
import { api } from "../lib/api";

interface Item { kind: string; id: string; title: string; created_at: string; status: string }
const KINDS = [["", "All"], ["recognition", "Recognition"], ["nutrition", "Nutrition"], ["freshness", "Freshness"], ["hygiene", "Hygiene"], ["recipe", "Recipes"], ["meal_plan", "Meal plans"]];
const link = (i: Item) => (i.kind === "nutrition" ? `/nutrition/${i.id}` : i.kind === "hygiene" ? `/hygiene/${i.id}` : ({ recognition: "/recognize", freshness: "/freshness", recipe: "/cooking", meal_plan: "/meal-planner" } as Record<string, string>)[i.kind]);

export default function History() {
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const size = 15;
  const q = useQuery({ queryKey: ["history", kind, page], queryFn: () => api<{ items: Item[]; total: number }>(`/history?page=${page}&page_size=${size}${kind ? `&kind=${kind}` : ""}`) });
  const pages = Math.max(1, Math.ceil((q.data?.total ?? 0) / size));
  return (
    <>
      <PageHeader title="Analysis History" intro="Everything you have analysed, newest first." />
      <div role="group" aria-label="Filter by type" className="mb-4 flex flex-wrap gap-1.5">
        {KINDS.map(([k, label]) => <button key={k} aria-pressed={kind === k} onClick={() => { setKind(k); setPage(1); }} className={`rounded-full px-3 py-1 text-sm font-semibold ${kind === k ? "bg-leaf text-white" : "bg-card border border-line hover:bg-leaf-soft"}`}>{label}</button>)}
      </div>
      {q.isPending && <Spinner />}
      <ErrorNotice error={q.error} />
      {q.data && (q.data.items.length === 0 ? <Empty title="Nothing here yet">Analyses you run will be listed here.</Empty> : (
        <Card className="p-0">
          <ul className="divide-y divide-line">{q.data.items.map((i) => (
            <li key={`${i.kind}-${i.id}`} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
              <div><Link to={link(i)} className="font-medium text-leaf hover:underline">{i.title}</Link><p className="text-xs text-muted">{fmtDate(i.created_at)}</p></div>
              <div className="flex gap-2"><Pill>{i.kind.replace("_", " ")}</Pill>{i.status !== "completed" && <Pill tone="warn">{i.status}</Pill>}</div>
            </li>))}
          </ul>
        </Card>
      ))}
      {pages > 1 && (
        <nav aria-label="Pagination" className="mt-4 flex items-center justify-center gap-3 text-sm">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span>Page {page} of {pages}</span>
          <Button variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
        </nav>
      )}
    </>
  );
}
