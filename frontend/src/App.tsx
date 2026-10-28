import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Protected } from "./lib/auth";
import Assistant from "./pages/Assistant";
import { Login, Register } from "./pages/AuthPages";
import Cooking from "./pages/Cooking";
import Dashboard from "./pages/Dashboard";
import Freshness from "./pages/Freshness";
import History from "./pages/History";
import Hygiene from "./pages/Hygiene";
import MealPlanner from "./pages/MealPlanner";
import Nutrition from "./pages/Nutrition";
import Recognition from "./pages/Recognition";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="assistant" element={<Assistant />} />
        <Route path="recognize" element={<Recognition />} />
        <Route path="nutrition" element={<Nutrition />} />
        <Route path="nutrition/:id" element={<Nutrition />} />
        <Route path="freshness" element={<Freshness />} />
        <Route path="hygiene" element={<Hygiene />} />
        <Route path="hygiene/:jobId" element={<Hygiene />} />
        <Route path="cooking" element={<Cooking />} />
        <Route path="meal-planner" element={<MealPlanner />} />
        <Route path="history" element={<History />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<p className="p-8">Page not found.</p>} />
    </Routes>
  );
}
