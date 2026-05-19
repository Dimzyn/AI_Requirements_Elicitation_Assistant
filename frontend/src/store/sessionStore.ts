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
};

export const useSessionStore = create<State>((set) => ({
  sessions: [],
  setSessions: (sessions) => set({ sessions }),
  activeId: null,
  setActive: (activeId) => set({ activeId, turns: [], requirements: [], status: "idle" }),
  turns: [],
  setTurns: (turns) => set({ turns }),
  appendTurns: (t) => set((s) => ({ turns: [...s.turns, ...t] })),
  requirements: [],
  setRequirements: (requirements) => set({ requirements }),
  status: "idle",
  setStatus: (status) => set({ status }),
}));
