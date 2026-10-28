import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, tokens } from "../lib/api";
import { Handler, meHandler, mockFetch, renderApp } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); tokens.clear(); });

const get = (url: string, json: unknown, status = 200): Handler => (r) => (r.url === url && r.method === "GET" ? { json, status } : undefined);
const post = (url: string, json: unknown, status = 200): Handler => (r) => (r.url === url && r.method !== "GET" ? { json, status } : undefined);
const png = () => new File([new Uint8Array([137, 80, 78, 71])], "dish.png", { type: "image/png" });

describe("auth", () => {
  it("redirects to login when signed out", async () => {
    mockFetch([]);
    renderApp("/recognize", { loggedIn: false });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("validates the login form before calling the server", async () => {
    const calls = mockFetch([]);
    renderApp("/login", { loggedIn: false });
    await userEvent.type(await screen.findByLabelText("Email"), "not-an-email");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(calls.filter((c) => c.url.includes("/auth/login"))).toHaveLength(0);
  });

  it("shows the server's error for wrong credentials", async () => {
    mockFetch([post("/api/v1/auth/login", { error: { code: "invalid_credentials", message: "Incorrect email or password" } }, 401)]);
    renderApp("/login", { loggedIn: false });
    await userEvent.type(await screen.findByLabelText("Email"), "a@b.co");
    await userEvent.type(screen.getByLabelText("Password"), "whatever-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
  });

  it("signs in and lands on the dashboard", async () => {
    mockFetch([post("/api/v1/auth/login", { access_token: "a", refresh_token: "r" }), meHandler,
      get("/api/v1/dashboard/summary", { counts: { recognition: 0 }, freshness_last_30d: {}, nutrition_trend_30d: [], hygiene_job_status: {}, alerts: [] }),
      get("/api/v1/history?page_size=6", { items: [] })]);
    renderApp("/login", { loggedIn: false });
    await userEvent.type(await screen.findByLabelText("Email"), "me@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: /Welcome, Asha/ })).toBeInTheDocument();
  });
});

describe("api client", () => {
  it("refreshes an expired access token once and retries", async () => {
    let first = true;
    const calls = mockFetch([
      (r) => (r.url === "/api/v1/ping" && first ? ((first = false), { status: 401, json: { error: { code: "token_expired", message: "Token expired" } } }) : undefined),
      post("/api/v1/auth/refresh", { access_token: "new", refresh_token: "r2" }),
      get("/api/v1/ping", { ok: true }),
    ]);
    tokens.set("old", "r1");
    expect(await api("/ping")).toEqual({ ok: true });
    expect(calls.map((c) => c.url)).toEqual(["/api/v1/ping", "/api/v1/auth/refresh", "/api/v1/ping"]);
    expect(localStorage.getItem("fv_refresh")).toBe("r2");
  });

  it("turns a network failure into a readable error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("failed"); }));
    await expect(api("/x")).rejects.toThrow("Cannot reach the server");
  });
});

describe("dashboard", () => {
  it("shows an empty state, not fake numbers, for a new user", async () => {
    mockFetch([meHandler, get("/api/v1/dashboard/summary", { counts: { recognition: 0, nutrition: 0 }, freshness_last_30d: {}, nutrition_trend_30d: [], hygiene_job_status: {}, alerts: [] }), get("/api/v1/history?page_size=6", { items: [] })]);
    renderApp("/");
    expect(await screen.findByText("Nothing analysed yet")).toBeInTheDocument();
  });

  it("renders real counts and alerts", async () => {
    mockFetch([meHandler, get("/api/v1/dashboard/summary", { counts: { recognition: 3, nutrition: 2 }, freshness_last_30d: {}, nutrition_trend_30d: [], hygiene_job_status: {}, alerts: [{ type: "hygiene_review", message: "2 hygiene finding(s) are waiting for human review." }] }),
      get("/api/v1/history?page_size=6", { items: [{ kind: "nutrition", id: "n1", title: "banana", created_at: "2026-10-01T10:00:00Z", status: "completed" }] })]);
    renderApp("/");
    expect(await screen.findByText(/2 hygiene finding/)).toBeInTheDocument();
    expect(screen.getByText("Recognitions").nextSibling).toHaveTextContent("3");
    expect(await screen.findByRole("link", { name: "banana" })).toHaveAttribute("href", "/nutrition/n1");
  });
});

describe("food recognition", () => {
  const analysis = { id: "a1", kind: "recognition", status: "completed", media_id: null, corrected: null, model_name: "food-vit", created_at: "2026-10-01T10:00:00Z",
    result: { top: { label: "pizza", confidence: 0.82 }, predictions: [{ label: "pizza", confidence: 0.82 }, { label: "hamburger", confidence: 0.09 }], notes: ["Low confidence: please confirm."] } };

  it("uploads, shows alternatives with confidence, and lets the user correct", async () => {
    mockFetch([meHandler, post("/api/v1/food/recognize", analysis, 201),
      (r) => (r.url === "/api/v1/food/recognize/a1/correction" ? { json: { ...analysis, corrected: { food_name: "calzone" } } } : undefined)]);
    renderApp("/recognize");
    const input = await screen.findByLabelText(/Choose a image file/);
    await userEvent.upload(input, png());
    await userEvent.click(screen.getByRole("button", { name: "Identify food" }));
    expect(await screen.findByRole("heading", { name: "pizza" })).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "hamburger" })).toHaveAttribute("aria-valuenow", "9");
    await userEvent.type(screen.getByLabelText(/Not right/), "calzone");
    await userEvent.click(screen.getByRole("button", { name: "Correct" }));
    expect(await screen.findByRole("heading", { name: "calzone" })).toBeInTheDocument();
    expect(screen.getByText(/Corrected by you/)).toBeInTheDocument();
  });

  it("tells the user when the model is not installed instead of faking a result", async () => {
    mockFetch([meHandler, post("/api/v1/food/recognize", { error: { code: "model_unavailable", message: "Food recognition model 'x' could not be loaded. Install the model weights." } }, 503)]);
    renderApp("/recognize");
    await userEvent.upload(await screen.findByLabelText(/Choose a image file/), png());
    await userEvent.click(screen.getByRole("button", { name: "Identify food" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
    expect(screen.queryByRole("heading", { name: "pizza" })).not.toBeInTheDocument();
  });

  it("keeps the identify button disabled until a file is chosen", async () => {
    mockFetch([meHandler]);
    renderApp("/recognize");
    expect(await screen.findByRole("button", { name: "Identify food" })).toBeDisabled();
  });
});

describe("nutrition", () => {
  const result = (over: object = {}) => ({ id: "n1", kind: "nutrition", status: "completed", created_at: "2026-10-01T10:00:00Z", result: {
    matched: true, food_name: "fried rice", match_score: 1, match_note: null, food: { name: "fried rice", source: "demo-seed", verified: false },
    portion: { grams: 198, estimated: true, basis: "default_serving" }, nutrients: { kcal: 322.7, protein_g: 8.1, carbs_g: 47.5, fat_g: 10.9, fiber_g: null, sugar_g: null },
    health_score: { score: 55, components: [{ criterion: "energy density", points: -5 }], skipped: ["fibre", "sugar"], criteria: "Simple heuristic" }, notes: ["Portion size is an estimate."], ...over } });

  it("shows unknown nutrients as unknown (never 0) and flags estimated portions", async () => {
    mockFetch([meHandler, post("/api/v1/nutrition/analyze", result(), 201)]);
    renderApp("/nutrition");
    await userEvent.type(await screen.findByLabelText("Food or dish"), "fried rice");
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    const fibre = (await screen.findByText("Fibre")).closest("div")!;
    expect(within(fibre).getByText("unknown")).toBeInTheDocument();
    expect(screen.getByText(/198 g · estimated portion/)).toBeInTheDocument();
    expect(screen.getByText(/Skipped \(unknown\): fibre, sugar/)).toBeInTheDocument();
  });

  it("validates the portion field", async () => {
    const calls = mockFetch([meHandler]);
    renderApp("/nutrition");
    await userEvent.type(await screen.findByLabelText("Food or dish"), "apple");
    await userEvent.type(screen.getByLabelText("Portion in grams"), "-4");
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByText(/Enter 1 to 5000 grams/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("nutrition/analyze"))).toBe(false);
  });

  it("says plainly when no record matches", async () => {
    mockFetch([meHandler, post("/api/v1/nutrition/analyze", { id: "n2", kind: "nutrition", result: { matched: false, message: "No nutrition record found for 'zzq'. Nothing was estimated." } }, 201)]);
    renderApp("/nutrition");
    await userEvent.type(await screen.findByLabelText("Food or dish"), "zzq");
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByText("No nutrition record found")).toBeInTheDocument();
  });
});

describe("freshness", () => {
  it("shows 'Unable to determine' with the reason and always the safety limits", async () => {
    mockFetch([meHandler, get("/api/v1/freshness/categories", { categories: [] }),
      post("/api/v1/freshness/analyze", { id: "f1", media_id: null, result: { state: "unable_to_determine", display: "Unable to determine", confidence: null, reason: "No freshness model is installed for 'paneer'.", recommendation: "Do not rely on it.", indicators: [], safety_note: "A visual check cannot show whether food is microbiologically safe." } }, 201)]);
    renderApp("/freshness");
    expect(await screen.findByText("No freshness models installed")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Food type"), "paneer");
    await userEvent.upload(screen.getByLabelText(/Choose a image file/), png());
    await userEvent.click(screen.getByRole("button", { name: "Check freshness" }));
    expect(await screen.findByRole("heading", { name: "Unable to determine" })).toBeInTheDocument();
    expect(screen.getByText(/No freshness model is installed for 'paneer'/)).toBeInTheDocument();
    expect(screen.getByText(/cannot show whether food is microbiologically safe/)).toBeInTheDocument();
  });
});

describe("hygiene", () => {
  it("uploads a video, polls the job to completion and shows an evidence-backed report with review controls", async () => {
    let polls = 0;
    const job = (status: string, progress: number, report_id: string | null) => ({ id: "j1", status, progress, video_meta: { duration_s: 10, width: 96, height: 96 }, error: null, created_at: "2026-10-01T10:00:00Z", report_id });
    const report = { report_id: "r1", job_id: "j1", status: "completed", video: {}, disclaimer: "This is not a food-safety inspection.", summary: { frames_analysed: 10, frame_interval_s: 1, detector: "fake", reliability: "Zero-shot." },
      findings: [{ id: "f1", indicator: "gloves", label: "Gloves visible on hands", status: "potential_violation_observed", confidence: 0.55, timestamp_s: 3, potential_concern: "Detected in 0 of 10 frames.", suggested_follow_up: "Review the clip.", evidence_media_id: null, review_status: "pending", review_note: null, detail: {} }] };
    const calls = mockFetch([meHandler, get("/api/v1/hygiene/jobs?page_size=10", { items: [], total: 0 }), post("/api/v1/hygiene/analyze", job("queued", 0, null), 202),
      (r) => (r.url === "/api/v1/hygiene/jobs/j1" && r.method === "GET" ? { json: ++polls < 2 ? job("running", 0.4, null) : job("completed", 1, "r1") } : undefined),
      get("/api/v1/hygiene/reports/r1", report),
      (r) => (r.url === "/api/v1/hygiene/findings/f1/review" ? { json: { id: "f1", review_status: "dismissed" } } : undefined)]);
    renderApp("/hygiene");
    await userEvent.upload(await screen.findByLabelText(/Choose a video file/), new File([new Uint8Array(8)], "kitchen.mp4", { type: "video/mp4" }));
    await userEvent.click(screen.getByRole("button", { name: "Start analysis" }));
    expect(await screen.findByText(/Analysing frames|Waiting for a worker/)).toBeInTheDocument();
    expect(await screen.findByText("Gloves visible on hands", {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByText("Potential concern observed")).toBeInTheDocument();
    expect(screen.getByText(/not a food-safety inspection/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/review") && c.body.review_status === "dismissed")).toBe(true));
  }, 15000);

  it("shows a failed job's reason", async () => {
    mockFetch([meHandler, get("/api/v1/hygiene/jobs?page_size=10", { items: [], total: 0 }),
      get("/api/v1/hygiene/jobs/j9", { id: "j9", status: "failed", progress: 0.2, video_meta: { duration_s: 5 }, error: "Hygiene detector could not be loaded.", created_at: "2026-10-01T10:00:00Z", report_id: null })]);
    renderApp("/hygiene/j9");
    expect(await screen.findByText("Processing failed")).toBeInTheDocument();
    expect(screen.getByText("Hygiene detector could not be loaded.")).toBeInTheDocument();
  });
});

describe("meal planner", () => {
  it("submits constraints, waits for generation, and shows the validated plan", async () => {
    let polls = 0;
    const plan = (status: string) => ({ id: "p1", status, params: {}, error: null, shopping_list: null, feedback: [], created_at: "2026-10-01T10:00:00Z",
      plan: status === "ready" ? { target_kcal_per_day: 2000, notes: ["AI-generated suggestions."], caveat: "Checked against names only.", days: [{ day: 1, daily_nutrition: { kcal_matched: 410, note: "Estimated." }, meals: [
        { meal_type: "breakfast", title: "Oats bowl", description: "", rationale: "Simple.", ingredients: [{ name: "banana", grams: 100 }], nutrition_estimate: { totals: { kcal: 89 }, complete: true, unmatched_ingredients: [] } }] }] } : {} });
    const calls = mockFetch([meHandler, post("/api/v1/meal-plans/generate", plan("generating"), 202),
      (r) => (r.url === "/api/v1/meal-plans/p1" && r.method === "GET" ? { json: ++polls < 2 ? plan("generating") : plan("ready") } : undefined)]);
    renderApp("/meal-planner");
    await userEvent.type(await screen.findByLabelText("Allergies"), "peanut, milk");
    await userEvent.click(screen.getByRole("button", { name: "Generate plan" }));
    expect(await screen.findByText("Generating your plan…")).toBeInTheDocument();
    expect(await screen.findByText("Oats bowl", {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByText(/Checked against names only/)).toBeInTheDocument();
    const sent = calls.find((c) => c.url.endsWith("/generate"))!.body;
    expect(sent.allergies).toEqual(["peanut", "milk"]);
    expect(sent.meals).toEqual(["breakfast", "lunch", "dinner"]);
  }, 15000);

  it("explains a failed plan instead of showing it", async () => {
    mockFetch([meHandler, post("/api/v1/meal-plans/generate", { id: "p2", status: "generating", plan: {}, params: {} }, 202),
      get("/api/v1/meal-plans/p2", { id: "p2", status: "failed", plan: {}, params: {}, error: "Generated plan violated your restrictions and was rejected" })]);
    renderApp("/meal-planner");
    await userEvent.click(await screen.findByRole("button", { name: "Generate plan" }));
    expect(await screen.findByText("The plan could not be completed")).toBeInTheDocument();
    expect(screen.getByText(/violated your restrictions/)).toBeInTheDocument();
  });

  it("requires at least one meal", async () => {
    const calls = mockFetch([meHandler]);
    renderApp("/meal-planner");
    for (const m of ["breakfast", "lunch", "dinner"]) await userEvent.click(await screen.findByLabelText(new RegExp(`^${m}$`, "i")));
    await userEvent.click(screen.getByRole("button", { name: "Generate plan" }));
    expect(await screen.findByText("Pick at least one meal")).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("generate"))).toBe(false);
  });
});

describe("cooking assistant", () => {
  it("generates a recipe and surfaces partial nutrition honestly", async () => {
    const recipe = { id: "r1", title: "Tomato rice", saved: false, parent_id: null, model_name: "qwen", created_at: "2026-10-01T10:00:00Z",
      data: { description: "Simple.", servings: 2, prep_minutes: 5, cook_minutes: 20, ingredients: [{ name: "rice", quantity: 200, unit: "g", grams: 200 }, { name: "mystery herb", grams: 5 }], steps: ["Boil rice."], tips: [], food_safety: ["Cool leftovers quickly."], substitutions: [] },
      meta: { nutrition_estimate: { complete: false, totals: { kcal: 260, protein_g: 5.4, carbs_g: 56.4, fat_g: 0.6 }, note: "Estimate from database-matched ingredients only.", unmatched_ingredients: ["mystery herb"] }, provenance: { note: "AI-generated." }, restriction_check: { applied: ["allergy: peanut"], caveat: "Check labels." } } };
    mockFetch([meHandler, get("/api/v1/recipes?saved=true&page_size=20", { items: [], total: 0 }), post("/api/v1/recipes/generate", recipe, 201)]);
    renderApp("/cooking");
    await userEvent.type(await screen.findByLabelText("Ingredients on hand"), "rice, tomato");
    await userEvent.click(screen.getByRole("button", { name: "Create recipe" }));
    expect(await screen.findByRole("heading", { name: "Tomato rice" })).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
    expect(screen.getByText(/Not matched: mystery herb/)).toBeInTheDocument();
    expect(screen.getByText(/Restrictions checked: allergy: peanut/)).toBeInTheDocument();
  });

  it("shows the restriction-violation refusal", async () => {
    mockFetch([meHandler, get("/api/v1/recipes?saved=true&page_size=20", { items: [], total: 0 }),
      post("/api/v1/recipes/generate", { error: { code: "restriction_violation", message: "A safe recipe that respects your restrictions could not be produced. Nothing was saved." } }, 422)]);
    renderApp("/cooking");
    await userEvent.click(await screen.findByRole("button", { name: "Create recipe" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was saved");
  });
});

describe("assistant, history, settings", () => {
  it("answers with labelled sources", async () => {
    mockFetch([meHandler, post("/api/v1/assistant/message", { intent: "nutrition", reply: "Banana (200 g): 178 kcal.", sources: [{ type: "user_provided", detail: "your message" }, { type: "database_fact", detail: "demo-seed" }], data: { analysis_id: "n1" }, action: null, transcript: null })]);
    renderApp("/assistant");
    await userEvent.type(await screen.findByLabelText("Message"), "calories in 200g banana");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Banana (200 g): 178 kcal.")).toBeInTheDocument();
    expect(screen.getByText("Database fact")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Details" })).toHaveAttribute("href", "/nutrition/n1");
  });

  it("paginates and filters history", async () => {
    const items = (n: number, start = 0) => Array.from({ length: n }, (_, i) => ({ kind: "nutrition", id: `n${start + i}`, title: `food ${start + i}`, created_at: "2026-10-01T10:00:00Z", status: "completed" }));
    const calls = mockFetch([meHandler, (r) => (r.url.startsWith("/api/v1/history?page=1") ? { json: { items: items(15), total: 20 } } : r.url.startsWith("/api/v1/history?page=2") ? { json: { items: items(5, 15), total: 20 } } : undefined)]);
    renderApp("/history");
    expect(await screen.findByText("food 0")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("food 15")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Recipes" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("kind=recipe"))).toBe(true));
  });

  it("saves profile restrictions as lists", async () => {
    const calls = mockFetch([meHandler, (r) => (r.url === "/api/v1/users/me/profile" ? { json: {} } : undefined)]);
    renderApp("/settings");
    await userEvent.type(await screen.findByLabelText(/^Allergies/), "peanut, shellfish");
    await userEvent.selectOptions(screen.getByLabelText("Dietary pattern"), "vegan");
    await userEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    expect(await screen.findByText("Preferences saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/profile"))!.body).toMatchObject({ allergies: ["peanut", "shellfish"], diet_pattern: "vegan" });
  });

  it("only enables account deletion after the email is typed", async () => {
    mockFetch([meHandler]);
    renderApp("/settings");
    const btn = await screen.findByRole("button", { name: "Delete everything" });
    expect(btn).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Type me@example.com to confirm/), "me@example.com");
    expect(btn).toBeEnabled();
  });
});
