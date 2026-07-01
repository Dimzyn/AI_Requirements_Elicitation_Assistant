import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { viewInvitation, acceptInvitation, type InvitationView } from "../api/invitations";
import { getMe } from "../api/auth";
import { useAuthStore } from "../store/authStore";
import { resetUserScopedStores } from "../store/authActions";

export default function InviteAcceptPage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);
  const setRole = useAuthStore((s) => s.setRole);

  const [info, setInfo] = useState<InvitationView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [realName, setRealName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    viewInvitation(token)
      .then(setInfo)
      .catch((e: { response?: { data?: { detail?: string } } }) =>
        setError(e?.response?.data?.detail ?? "This invitation is invalid or expired.")
      );
  }, [token]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const access = await acceptInvitation(
        token,
        password,
        realName || undefined,
        jobTitle || undefined
      );
      // Joining as a new stakeholder must start clean — clear any prior account's
      // in-memory chat/requirements left over from this browser tab.
      resetUserScopedStores();
      setToken(access);
      const me = await getMe();
      setRole(me.role);
      navigate("/", { replace: true });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err?.response?.data?.detail ?? "Could not accept the invitation.");
      setSubmitting(false);
    }
  }

  if (error && !info)
    return (
      <div className="grid min-h-screen place-items-center bg-background p-6">
        <p className="text-sm text-muted">{error}</p>
      </div>
    );

  if (!info)
    return (
      <div className="grid min-h-screen place-items-center bg-background p-6">
        <p className="text-sm text-muted">Loading…</p>
      </div>
    );

  return (
    <div className="grid min-h-screen place-items-center bg-background p-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-2xl border border-border bg-surface p-8 shadow-lift space-y-4"
      >
        <h1 className="text-lg font-semibold text-foreground">Join "{info.project_title}"</h1>
        <p className="text-sm text-muted">
          Invitation for {info.email}. Choose a name and set a password to continue.
        </p>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="Your name (shown to the requirements engineer)"
          value={realName}
          required
          onChange={(e) => setRealName(e.target.value)}
        />
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="Your role (e.g. Product Owner, End User)"
          value={jobTitle}
          required
          onChange={(e) => setJobTitle(e.target.value)}
        />
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          type="password"
          placeholder="Password (min 8 chars)"
          value={password}
          minLength={8}
          required
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <div className="rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-accent py-2.5 text-sm font-semibold text-accent-foreground shadow-sm transition hover:brightness-110 disabled:opacity-50"
        >
          {submitting ? "Joining…" : "Join project"}
        </button>
      </form>
    </div>
  );
}
