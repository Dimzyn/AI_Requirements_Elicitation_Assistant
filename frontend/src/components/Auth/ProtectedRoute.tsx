import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { getMe } from "../../api/auth";

export default function ProtectedRoute() {
  const token = useAuthStore((s) => s.token);
  const setRole = useAuthStore((s) => s.setRole);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then((p) => setRole(p.role))
      .catch(() => useAuthStore.getState().clear())
      .finally(() => setLoading(false));
  }, [token]);

  if (!token) return <Navigate to="/login" replace />;
  if (loading)
    return (
      <div className="h-screen flex items-center justify-center text-slate-500">
        Loading...
      </div>
    );
  return <Outlet />;
}
