import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useSessionStore } from "../store/sessionStore";
import { useAuthStore } from "../store/authStore";
import { getTurns, getRequirements } from "../api/sessions";
import ProjectSidebar from "../components/Sidebar/ProjectSidebar";
import ChatPanel from "../components/Dialogue/ChatPanel";
import InputBox from "../components/Dialogue/InputBox";
import LiveRequirements from "../components/Requirements/LiveRequirements";
import AppHeader from "../components/AppHeader";

export default function MainPage() {
  const [params] = useSearchParams();
  const sessionParam = params.get("session");
  const setActive = useSessionStore((s) => s.setActive);
  const activeId = useSessionStore((s) => s.activeId);
  const setTurns = useSessionStore((s) => s.setTurns);
  const setRequirements = useSessionStore((s) => s.setRequirements);
  const role = useAuthStore((s) => s.role);

  useEffect(() => {
    if (sessionParam) setActive(sessionParam);
  }, [sessionParam, setActive]);

  useEffect(() => {
    if (!activeId) return;
    let active = true;
    (async () => {
      try {
        const turns = await getTurns(activeId);
        if (active) setTurns(turns);
        if (role === "requirements_engineer") {
          const reqs = await getRequirements(activeId);
          if (active) setRequirements(reqs);
        }
      } catch {
        /* ignore */
      }
    })();
    return () => { active = false; };
  }, [activeId, role, setTurns, setRequirements]);

  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader title="Probing Generator" />
      {role === "requirements_engineer" ? (
        <div className="grid grid-cols-[248px_1fr_312px] overflow-hidden">
          <ProjectSidebar />
          <main className="flex flex-col overflow-hidden bg-surface-muted">
            <ChatPanel />
            <InputBox />
          </main>
          <LiveRequirements />
        </div>
      ) : (
        <div className="grid grid-cols-[248px_1fr] overflow-hidden">
          <ProjectSidebar />
          <main className="flex flex-col overflow-hidden bg-surface-muted">
            <ChatPanel />
            <InputBox />
          </main>
        </div>
      )}
    </div>
  );
}
