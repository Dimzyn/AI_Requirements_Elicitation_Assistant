import { create } from "zustand";
import type { SreRequirement } from "../api/requirements";
import type { Session } from "../api/sessions";

type SpecState = {
  sessions: Session[];
  setSessions: (s: Session[]) => void;
  requirements: SreRequirement[];
  setRequirements: (r: SreRequirement[]) => void;
  updateRequirement: (r: SreRequirement) => void;
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  filterSessionId: string | null;
  setFilterSessionId: (id: string | null) => void;
  filterStatus: string | null;
  setFilterStatus: (s: string | null) => void;
  filterType: string | null;
  setFilterType: (t: string | null) => void;
};

export const useSpecStore = create<SpecState>((set) => ({
  sessions: [],
  setSessions: (sessions) => set({ sessions }),
  requirements: [],
  setRequirements: (requirements) => set({ requirements }),
  updateRequirement: (updated) =>
    set((s) => ({
      requirements: s.requirements.map((r) => (r.id === updated.id ? updated : r)),
    })),
  selectedId: null,
  setSelectedId: (selectedId) => set({ selectedId }),
  filterSessionId: null,
  setFilterSessionId: (filterSessionId) => set({ filterSessionId }),
  filterStatus: null,
  setFilterStatus: (filterStatus) => set({ filterStatus }),
  filterType: null,
  setFilterType: (filterType) => set({ filterType }),
}));
