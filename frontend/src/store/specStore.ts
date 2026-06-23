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
  reset: () => void;
};

const INITIAL = {
  sessions: [] as Session[],
  requirements: [] as SreRequirement[],
  selectedId: null as string | null,
  filterSessionId: null as string | null,
  filterStatus: null as string | null,
  filterType: null as string | null,
};

export const useSpecStore = create<SpecState>((set) => ({
  ...INITIAL,
  setSessions: (sessions) => set({ sessions }),
  setRequirements: (requirements) => set({ requirements }),
  updateRequirement: (updated) =>
    set((s) => ({
      requirements: s.requirements.map((r) => (r.id === updated.id ? updated : r)),
    })),
  setSelectedId: (selectedId) => set({ selectedId }),
  setFilterSessionId: (filterSessionId) => set({ filterSessionId }),
  setFilterStatus: (filterStatus) => set({ filterStatus }),
  setFilterType: (filterType) => set({ filterType }),
  // Wipe the curator view's data + filters on auth changes.
  reset: () => set({ ...INITIAL }),
}));
