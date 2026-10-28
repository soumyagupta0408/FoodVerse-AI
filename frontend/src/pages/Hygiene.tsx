import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AuthedImage, Button, Card, ConfidenceBar, Empty, ErrorNotice, FileDrop, fmtDate, Limits, Notice, PageHeader, Pill, Spinner } from "../components/ui";
import { api } from "../lib/api";
import type { Finding, HygieneReport, Job, Page } from "../lib/types";

const STATUS_TEXT: Record<string, [string, "good" | "warn" | "bad" | "neutral"]> = {
  observed_compliance: ["Observed compliance", "good"], potential_violation_observed: ["Potential concern observed", "bad"],
  insufficient_evidence: ["Insufficient evidence", "neutral"], not_applicable: ["Not applicable", "neutral"],
};
const JOB_TONE = { queued: "neutral", running: "warn", completed: "good", failed: "bad", cancelled: "neutral" } as const;

function FindingCard({ f, onReview }: { f: Finding; onReview: (id: string, s: string) => void }) {
  const [text, tone] = STATUS_TEXT[f.status] ?? [f.status, "neutral" as const];
  return (
    <li className="rounded-lg border border-line p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{f.label}</h3><Pill tone={tone}>{text}</Pill></div>
      {f.confidence != null && <div className="mt-2 max-w-xs"><ConfidenceBar value={f.confidence} label="Detector confidence (unvalidated)" /></div>}
      {f.timestamp_s != null && <p className="mt-2 text-xs text-muted">Evidence frame at {f.timestamp_s.toFixed(1)} s</p>}
      {f.evidence_media_id && <div className="mt-2"><AuthedImage mediaId={f.evidence_media_id} alt={`Evidence frame for ${f.label}`} className="max-h-48" /></div>}
      {f.potential_concern && <p className="mt-2 text-sm">{f.potential_concern}</p>}
      {f.suggested_follow_up && <p className="mt-1 text-sm text-muted">Follow-up: {f.suggested_follow_up}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">Human review:</span><Pill tone={f.review_status === "pending" ? "warn" : "neutral"}>{f.review_status}</Pill>
        {f.review_status === "pending" && <><Button variant="secondary" onClick={() => onReview(f.id, "confirmed")}>Confirm concern</Button><Button variant="ghost" onClick={() => onReview(f.id, "dismissed")}>Dismiss</Button></>}
      </div>
    </li>
  );
}

function JobView({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const job = useQuery({ queryKey: ["hjob", jobId], queryFn: () => api<Job>(`/hygiene/jobs/${jobId}`),
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.status) ? 2000 : false) });
  const rid = job.data?.report_id;
  const report = useQuery({ queryKey: ["hreport", rid], queryFn: () => api<HygieneReport>(`/hygiene/reports/${rid}`), enabled: !!rid });
  const cancel = useMutation({ mutationFn: () => api<Job>(`/hygiene/jobs/${jobId}/cancel`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["hjob", jobId] }) });
  const del = useMutation({ mutationFn: () => api<void>(`/hygiene/jobs/${jobId}`, { method: "DELETE" }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["hjobs"] }); nav("/hygiene"); } });
  const review = useMutation({ mutationFn: (v: { id: string; s: string }) => api(`/hygiene/findings/${v.id}/review`, { method: "PATCH", json: { review_status: v.s } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["hreport", rid] }) });

  if (job.isPending) return <Spinner />;
  if (job.isError) return <ErrorNotice error={job.error} />;
  const j = job.data;
  const active = j.status === "queued" || j.status === "running";
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2"><h2 className="text-xl font-semibold">Analysis job</h2><Pill tone={JOB_TONE[j.status]}>{j.status}</Pill></div>
          <div className="flex gap-2">
            {active && <Button variant="secondary" loading={cancel.isPending} onClick={() => cancel.mutate()}>Cancel</Button>}
            {!active && <Button variant="ghost" loading={del.isPending} onClick={() => { if (confirm("Delete this job, its report, evidence frames and the uploaded video?")) del.mutate(); }}>Delete</Button>}
          </div>
        </div>
        {active && (
          <div className="mt-3" aria-live="polite">
            <ConfidenceBar value={j.progress} label={j.status === "queued" ? "Waiting for a worker…" : "Analysing frames"} />
            {j.status === "queued" && <p className="mt-1 text-xs text-muted">If this stays queued, check that the worker process is running.</p>}
          </div>
        )}
        <p className="mt-2 text-xs text-muted">Video {j.video_meta.duration_s}s, {j.video_meta.width}×{j.video_meta.height} · submitted {fmtDate(j.created_at)}</p>
        {j.status === "failed" && <div className="mt-3"><Notice tone="bad" title="Processing failed">{j.error}</Notice></div>}
        {j.status === "cancelled" && <div className="mt-3"><Notice>This job was cancelled. No report was produced.</Notice></div>}
        <ErrorNotice error={cancel.error ?? del.error ?? review.error} />
      </Card>
      {report.data && (
        <Card>
          <h2 className="text-xl font-semibold">Report</h2>
          <div className="my-3"><Limits title="Read this first">{report.data.disclaimer}</Limits></div>
          <p className="mb-3 text-sm text-muted">{report.data.summary.frames_analysed} frames analysed every {report.data.summary.frame_interval_s}s using {report.data.summary.detector}. {report.data.summary.reliability}</p>
          <ul className="space-y-3">{report.data.findings.map((f) => <FindingCard key={f.id} f={f} onReview={(id, s) => review.mutate({ id, s })} />)}</ul>
        </Card>
      )}
    </div>
  );
}

export default function Hygiene() {
  const { jobId } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const jobs = useQuery({ queryKey: ["hjobs"], queryFn: () => api<Page<Job>>("/hygiene/jobs?page_size=10") });
  const up = useMutation({ mutationFn: () => { const f = new FormData(); f.append("file", file!); return api<Job>("/hygiene/analyze", { form: f }); },
    onSuccess: (j) => { qc.invalidateQueries({ queryKey: ["hjobs"] }); setFile(null); nav(`/hygiene/${j.id}`); } });

  return (
    <>
      <PageHeader title="Restaurant Hygiene" intro="Upload kitchen video to get observable hygiene indicators with evidence frames, for a person to review." />
      <div className="grid gap-6 md:grid-cols-[20rem_1fr]">
        <div className="space-y-4">
          <Card>
            <FileDrop kind="video" accept="video/mp4,video/quicktime,video/webm,video/x-msvideo" file={file} onFile={setFile} hint="MP4, MOV, WEBM or AVI, up to 200 MB / 15 min" />
            <Button className="mt-4 w-full" disabled={!file} loading={up.isPending} onClick={() => up.mutate()}>Start analysis</Button>
            <div className="mt-3"><ErrorNotice error={up.error} /></div>
          </Card>
          <Card>
            <h2 className="mb-2 text-lg font-semibold">Recent jobs</h2>
            {jobs.isPending ? <Spinner small /> : jobs.data?.items.length ? (
              <ul className="space-y-1 text-sm">{jobs.data.items.map((j) => (
                <li key={j.id}><Link to={`/hygiene/${j.id}`} className="flex items-center justify-between rounded px-2 py-1 hover:bg-leaf-soft"><span>{fmtDate(j.created_at)}</span><Pill tone={JOB_TONE[j.status]}>{j.status}</Pill></Link></li>))}</ul>
            ) : <p className="text-sm text-muted">No jobs yet.</p>}
          </Card>
        </div>
        <div>{jobId ? <JobView jobId={jobId} /> : <Empty title="No job selected">Upload a video or pick a recent job. Findings are potential concerns for human review: they are not compliance verdicts and not proof that anyone broke a rule.</Empty>}</div>
      </div>
    </>
  );
}
