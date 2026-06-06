import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useSessionStore } from "../store/sessionStore";
import ProjectSidebar from "../components/Sidebar/ProjectSidebar";
import ChatPanel from "../components/Dialogue/ChatPanel";
import InputBox from "../components/Dialogue/InputBox";
import LiveRequirements from "../components/Requirements/LiveRequirements";
import AppHeader from "../components/AppHeader";

export default function MainPage() {
  const [params] = useSearchParams();
  const sessionParam = params.get("session");
  const setActive = useSessionStore((s) => s.setActive);

  useEffect(() => {
    if (sessionParam) setActive(sessionParam);
  }, [sessionParam, setActive]);

  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader title="Probing Generator" />
      <div className="grid grid-cols-[248px_1fr_312px] overflow-hidden">
        <ProjectSidebar />
        <main className="flex flex-col overflow-hidden bg-surface-muted">
          <ChatPanel />
          <InputBox />
        </main>
        <LiveRequirements />
      </div>
    </div>
  );
}
