import { useAuthStore } from "../store/authStore";
import { useNavigate } from "react-router-dom";

export default function MainPage() {
  const clear = useAuthStore((s) => s.clear);
  const nav = useNavigate();
  return (
    <div className="min-h-screen p-8 bg-slate-50">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">AI Probing Question Generator</h1>
        <button
          onClick={() => {
            clear();
            nav("/login");
          }}
          className="px-3 py-1 border rounded text-sm"
        >
          Log out
        </button>
      </div>
      <p className="mt-8 text-slate-600">
        You are signed in. The interview workspace is being built (Task 6.3).
      </p>
    </div>
  );
}
