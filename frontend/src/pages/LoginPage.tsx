import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login } from "../api/auth";
import { useAuthStore } from "../store/authStore";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const setToken = useAuthStore((s) => s.setToken);
  const nav = useNavigate();

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const token = await login({ email, password });
      setToken(token);
      nav("/");
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErr(detail ?? "Login failed");
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-background bg-[radial-gradient(700px_360px_at_18%_-8%,rgb(var(--accent)/0.10),transparent_60%),radial-gradient(600px_340px_at_100%_110%,rgb(124_58_237/0.08),transparent_60%)] p-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-2xl border border-border bg-surface p-8 shadow-lift"
      >
        <div className="mb-1 flex items-center justify-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg text-accent-foreground shadow-sm">
            ◆
          </span>
          <span className="font-semibold text-foreground">Probing Generator</span>
        </div>
        <h1 className="mt-3 text-center text-xl font-semibold text-foreground">
          Welcome back
        </h1>
        <p className="mb-6 mt-2 text-center text-sm text-muted">
          Sign in to continue your requirements interviews.
        </p>

        <label className="mb-1.5 mt-3 block text-xs font-semibold text-muted">
          Email
        </label>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="you@company.com"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label className="mb-1.5 mt-3.5 block text-xs font-semibold text-muted">
          Password
        </label>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="••••••••"
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {err && (
          <div className="mt-3.5 rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">
            {err}
          </div>
        )}

        <button
          type="submit"
          className="mt-5 w-full rounded-lg bg-accent py-2.5 text-sm font-semibold text-accent-foreground shadow-sm transition hover:brightness-110"
        >
          Sign in
        </button>

        <p className="mt-4 text-center text-sm text-muted">
          Don't have an account?{" "}
          <Link to="/signup" className="font-semibold text-accent hover:underline">
            Create one
          </Link>
        </p>
      </form>
    </div>
  );
}
