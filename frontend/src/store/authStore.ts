import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

type AuthState = {
  token: string | null;
  role: "stakeholder" | "requirements_engineer" | null;
  name: string | null;
  jobTitle: string | null;
  setToken: (token: string | null) => void;
  setRole: (role: "stakeholder" | "requirements_engineer" | null) => void;
  setProfile: (p: { name: string | null; jobTitle: string | null }) => void;
  clear: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      name: null,
      jobTitle: null,
      setToken: (token) => set({ token }),
      setRole: (role) => set({ role }),
      setProfile: ({ name, jobTitle }) => set({ name, jobTitle }),
      clear: () => set({ token: null, role: null, name: null, jobTitle: null }),
    }),
    {
      name: "probing-auth",
      // Per-tab storage so a Requirements Engineer and a Stakeholder can be signed in
      // side-by-side in the same browser. localStorage is shared across every tab, so a
      // second login there overwrites the first and crashes the other tab on refresh.
      storage: createJSONStorage(() => sessionStorage),
    }
  )
);
