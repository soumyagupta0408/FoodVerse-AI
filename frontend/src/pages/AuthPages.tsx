import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button, ErrorNotice, TextInput } from "../components/ui";
import { useAuth } from "../lib/auth";

const loginSchema = z.object({ email: z.string().email("Enter a valid email address"), password: z.string().min(1, "Enter your password") });
const registerSchema = z.object({
  display_name: z.string().max(100).optional(),
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(10, "Use at least 10 characters").max(128),
});

function Shell({ title, children, footer }: { title: string; children: React.ReactNode; footer: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <p className="font-display text-xl font-semibold text-leaf">FoodVerse AI</p>
      <h1 className="mb-6 mt-1 text-3xl font-semibold">{title}</h1>
      {children}
      <p className="mt-6 text-sm text-muted">{footer}</p>
    </div>
  );
}

export function Login() {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [error, setError] = useState<unknown>(null);
  const f = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema) });
  const go = f.handleSubmit(async (v) => {
    setError(null);
    try { await signIn(v.email, v.password); nav((loc.state as any)?.from ?? "/", { replace: true }); } catch (e) { setError(e); }
  });
  return (
    <Shell title="Sign in" footer={<>New here? <Link className="font-semibold text-leaf underline" to="/register">Create an account</Link></>}>
      <form onSubmit={go} className="space-y-4" noValidate>
        <TextInput label="Email" type="email" autoComplete="email" error={f.formState.errors.email?.message} {...f.register("email")} />
        <TextInput label="Password" type="password" autoComplete="current-password" error={f.formState.errors.password?.message} {...f.register("password")} />
        <ErrorNotice error={error} />
        <Button type="submit" loading={f.formState.isSubmitting} className="w-full">Sign in</Button>
      </form>
    </Shell>
  );
}

export function Register() {
  const { signUp } = useAuth();
  const nav = useNavigate();
  const [error, setError] = useState<unknown>(null);
  const f = useForm<z.infer<typeof registerSchema>>({ resolver: zodResolver(registerSchema) });
  const go = f.handleSubmit(async (v) => {
    setError(null);
    try { await signUp(v.email, v.password, v.display_name); nav("/", { replace: true }); } catch (e) { setError(e); }
  });
  return (
    <Shell title="Create your account" footer={<>Already registered? <Link className="font-semibold text-leaf underline" to="/login">Sign in</Link></>}>
      <form onSubmit={go} className="space-y-4" noValidate>
        <TextInput label="Name (optional)" autoComplete="name" {...f.register("display_name")} />
        <TextInput label="Email" type="email" autoComplete="email" error={f.formState.errors.email?.message} {...f.register("email")} />
        <TextInput label="Password" type="password" autoComplete="new-password" hint="At least 10 characters." error={f.formState.errors.password?.message} {...f.register("password")} />
        <ErrorNotice error={error} />
        <Button type="submit" loading={f.formState.isSubmitting} className="w-full">Create account</Button>
      </form>
    </Shell>
  );
}
