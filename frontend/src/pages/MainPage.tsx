import { useEffect } from "react";
import { useSessionStore } from "../store/sessionStore";
import SessionList from "../components/Sidebar/SessionList";
import ChatPanel from "../components/Dialogue/ChatPanel";
import InputBox from "../components/Dialogue/InputBox";
import LiveRequirements from "../components/Requirements/LiveRequirements";
import AppHeader from "../components/AppHeader";

export default function MainPage() {
  // Land the stakeholder straight in the draft welcome state so the AI greeting
  // is visible immediately — no need to click "New Session" first.
  useEffect(() => {
    const { activeId, draft, setDraft } = useSessionStore.getState();
    if (!activeId && !draft) setDraft(true);
  }, []);

  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader title="Probing Generator" />
      <div className="grid grid-cols-[248px_1fr_312px] overflow-hidden">
        <SessionList />
        <main className="flex flex-col overflow-hidden bg-surface-muted">
          <ChatPanel />
          <InputBox />
        </main>
        <LiveRequirements />
      </div>
    </div>
  );
}
