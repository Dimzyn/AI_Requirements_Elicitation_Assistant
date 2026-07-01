import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { getMe } from "../../api/auth";

export default function ProtectedRoute() {
  const token = useAuthStore((s) => s.token);
  const setRole = useAuthStore((s) => s.setRole);
  const setProfile = useAuthStore((s) => s.setProfile);
  // Only the token-present path needs to fetch /me, so start "loading" only then.
  const [loading, setLoading] = useState(Boolean(token));

  useEffect(() => {
    if (!token) return;
    getMe()
      .then((p) => {
        setRole(p.role);
        setProfile({ name: p.real_name, jobTitle: p.job_title });
      })
      .catch(() => useAuthStore.getState().clear())
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (!token) return <Navigate to="/login" replace />;
  if (loading)
    return (
      <div className="h-screen flex items-center justify-center bg-background text-muted">
        Loading...
      </div>
    );
  return <Outlet />;
}
