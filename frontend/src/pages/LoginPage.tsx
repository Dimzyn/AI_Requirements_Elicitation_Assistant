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
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <form onSubmit={onSubmit} className="w-96 p-8 bg-white rounded-2xl shadow space-y-4">
        <h1 className="text-2xl font-semibold">Login</h1>
        <input
          className="w-full border rounded p-2"
          placeholder="Email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className="w-full border rounded p-2"
          placeholder="Password"
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {err && <p className="text-red-600 text-sm">{err}</p>}
        <button type="submit" className="w-full bg-indigo-600 text-white rounded p-2 font-medium hover:bg-indigo-700">
          Login
        </button>
        <p className="text-sm text-right">
          <Link to="/signup" className="text-indigo-600 hover:underline">
            Create an account
          </Link>
        </p>
      </form>
    </div>
  );
}
