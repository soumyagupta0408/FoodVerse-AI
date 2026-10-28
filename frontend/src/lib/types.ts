export interface Profile {
  display_name: string | null;
  diet_pattern: string | null;
  allergies: string[];
  excluded_ingredients: string[];
  nutrition_goals: Record<string, unknown>;
  cuisines: string[];
}
export interface User { id: string; email: string; role: string; profile: Profile | null }
export interface Analysis {
  id: string; kind: "recognition" | "nutrition" | "freshness"; status: string; media_id: string | null; parent_id: string | null;
  input: Record<string, any>; result: Record<string, any>; corrected: { food_name: string } | null;
  model_name: string | null; model_version: string | null; error: string | null; created_at: string;
}
export interface Job { id: string; status: "queued" | "running" | "completed" | "failed" | "cancelled"; progress: number; video_meta: Record<string, any>; error: string | null; created_at: string; report_id: string | null }
export interface Finding {
  id: string; indicator: string; label: string; status: string; confidence: number | null; timestamp_s: number | null;
  potential_concern: string | null; suggested_follow_up: string | null; evidence_media_id: string | null; review_status: string; review_note: string | null;
}
export interface HygieneReport { report_id: string; job_id: string; status: string; video: Record<string, any>; summary: Record<string, any>; disclaimer: string; findings: Finding[] }
export interface Recipe { id: string; title: string; data: Record<string, any>; saved: boolean; parent_id: string | null; model_name: string | null; created_at: string; meta: Record<string, any> }
export interface MealPlan { id: string; status: "generating" | "ready" | "failed"; params: Record<string, any>; plan: Record<string, any>; shopping_list: any[] | null; error: string | null; feedback: any[]; created_at: string }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface Reply { intent: string; reply: string; sources: { type: string; detail: string }[]; data: any; action: { type: string; path: string; prefill?: Record<string, unknown> } | null; transcript: string | null }
