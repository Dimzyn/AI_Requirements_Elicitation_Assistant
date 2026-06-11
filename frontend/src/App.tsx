import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import MainPage from "./pages/MainPage";
import SpecPage from "./pages/SpecPage";
import InviteAcceptPage from "./pages/InviteAcceptPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import ProtectedRoute from "./components/Auth/ProtectedRoute";
import { useAuthStore } from "./store/authStore";

function RoleRedirect() {
  const role = useAuthStore((s) => s.role);
  if (role === "requirements_engineer") return <Navigate to="/projects" replace />;
  return <Navigate to="/chat" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/invite/:token" element={<InviteAcceptPage />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<RoleRedirect />} />
          <Route path="/chat" element={<MainPage />} />
          <Route path="/spec" element={<SpecPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
          <Route path="/projects/:id/spec" element={<SpecPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
