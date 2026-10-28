import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Button } from "./ui";

const NAV: [string, string][] = [
  ["/", "Dashboard"], ["/assistant", "Assistant"], ["/recognize", "Food Recognition"], ["/nutrition", "Nutrition Analyzer"], ["/freshness", "Freshness Checker"],
  ["/hygiene", "Restaurant Hygiene"], ["/cooking", "Cooking Assistant"], ["/meal-planner", "Meal Planner"], ["/history", "Analysis History"], ["/settings", "Profile & Settings"],
];

export default function Layout() {
  const [open, setOpen] = useState(false);
  const { user, signOut } = useAuth();
  const nav = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-leaf text-white" : "text-ink hover:bg-leaf-soft"}`;
  return (
    <div className="min-h-screen md:grid md:grid-cols-[15rem_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:p-2">Skip to content</a>
      <div className="flex items-center justify-between border-b border-line bg-card px-4 py-3 md:hidden">
        <span className="font-display text-lg font-semibold">FoodVerse AI</span>
        <Button variant="secondary" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(!open)}>{open ? "Close" : "Menu"}</Button>
      </div>
      <aside id="sidebar" className={`${open ? "block" : "hidden"} border-r border-line bg-card p-4 md:sticky md:top-0 md:block md:h-screen md:overflow-y-auto`}>
        <p className="mb-4 hidden font-display text-xl font-semibold md:block">FoodVerse AI</p>
        <nav aria-label="Main" className="space-y-1">
          {NAV.map(([to, label]) => (<NavLink key={to} to={to} end={to === "/"} className={link} onClick={() => setOpen(false)}>{label}</NavLink>))}
        </nav>
        <div className="mt-6 border-t border-line pt-4 text-xs text-muted">
          <p className="truncate" title={user?.email}>{user?.email}</p>
          <button className="mt-2 font-semibold text-leaf underline" onClick={async () => { await signOut(); nav("/login"); }}>Sign out</button>
        </div>
      </aside>
      <main id="main" className="mx-auto w-full max-w-5xl px-4 py-8 md:px-8"><Outlet /></main>
    </div>
  );
}
