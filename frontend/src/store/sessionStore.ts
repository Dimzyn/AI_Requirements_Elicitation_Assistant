import { create } from "zustand";
import type { Session, Turn, Requirement } from "../api/sessions";

type Status = "idle" | "thinking" | "validating";

type State = {
  sessions: Session[];
  setSessions: (s: Session[]) => void;
  activeId: string | null;
  setActive: (id: string | null) => void;
  draft: boolean;
  setDraft: (v: boolean) => void;
  // One-shot guard: when a session is created mid-send, suppress the next
  // auto-load of its turns so the optimistic bubbles aren't clobbered.
  skipNextTurnLoad: boolean;
  setSkipNextTurnLoad: (v: boolean) => void;
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
  setActive: (activeId) =>
    set((s) =>
      s.activeId === activeId
        ? { draft: false }
        : { activeId, draft: false, turns: [], requirements: [], status: "idle" }
    ),
  draft: false,
  // Entering draft mode clears the active session and shows the welcome greeting.
  setDraft: (draft) =>
    set(
      draft
        ? { draft: true, activeId: null, turns: [], requirements: [], status: "idle" }
        : { draft: false }
    ),
  skipNextTurnLoad: false,
  setSkipNextTurnLoad: (skipNextTurnLoad) => set({ skipNextTurnLoad }),
  turns: [],
  setTurns: (turns) => set({ turns }),
  appendTurns: (t) => set((s) => ({ turns: [...s.turns, ...t] })),
  requirements: [],
  setRequirements: (requirements) => set({ requirements }),
  status: "idle",
  setStatus: (status) => set({ status }),
}));
