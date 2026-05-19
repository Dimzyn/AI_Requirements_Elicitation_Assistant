import { useAuthStore } from "../store/authStore";
import { useNavigate } from "react-router-dom";
import SessionList from "../components/Sidebar/SessionList";
import ChatPanel from "../components/Dialogue/ChatPanel";
import InputBox from "../components/Dialogue/InputBox";
import LiveRequirements from "../components/Requirements/LiveRequirements";

export default function MainPage() {
  const clear = useAuthStore((s) => s.clear);
  const nav = useNavigate();

  return (
    <div className="h-screen grid grid-rows-[auto_1fr] bg-slate-50">
      <header className="bg-white border-b px-4 py-2 flex items-center justify-between">
        <h1 className="font-semibold text-slate-800">AI Probing Question Generator</h1>
        <button
          onClick={() => {
            clear();
            nav("/login");
          }}
          className="text-sm px-3 py-1 border rounded hover:bg-slate-100"
        >
          Log out
        </button>
      </header>
      <div className="grid grid-cols-[260px_1fr_320px] overflow-hidden">
        <SessionList />
        <main className="flex flex-col overflow-hidden">
          <ChatPanel />
          <InputBox />
        </main>
        <LiveRequirements />
      </div>
    </div>
  );
}
