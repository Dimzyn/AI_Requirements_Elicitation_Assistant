import { create } from "zustand";
import type { Session, Turn, Requirement } from "../api/sessions";

type Status = "idle" | "thinking" | "validating";

type State = {
  sessions: Session[];
  setSessions: (s: Session[]) => void;
  activeId: string | null;
  setActive: (id: string | null) => void;
  turns: Turn[];
  setTurns: (t: Turn[]) => void;
  appendTurns: (t: Turn[]) => void;
  requirements: Requirement[];
  setRequirements: (r: Requirement[]) => void;
  status: Status;
  setStatus: (s: Status) => void;
  reset: () => void;
};

const INITIAL = {
  sessions: [] as Session[],
  activeId: null as string | null,
  turns: [] as Turn[],
  requirements: [] as Requirement[],
  status: "idle" as Status,
};

export const useSessionStore = create<State>((set) => ({
  ...INITIAL,
  setSessions: (sessions) => set({ sessions }),
  setActive: (activeId) =>
    set((s) =>
      s.activeId === activeId
        ? {}
        : { activeId, turns: [], requirements: [], status: "idle" }
    ),
  setTurns: (turns) => set({ turns }),
  appendTurns: (t) => set((s) => ({ turns: [...s.turns, ...t] })),
  setRequirements: (requirements) => set({ requirements }),
  setStatus: (status) => set({ status }),
  // Wipe all session/chat state — called on auth changes so one account's
  // chat history never persists into the next.
  reset: () => set({ ...INITIAL }),
}));
