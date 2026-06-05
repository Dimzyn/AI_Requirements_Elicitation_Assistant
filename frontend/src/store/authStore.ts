import { create } from "zustand";
import { persist } from "zustand/middleware";

type AuthState = {
  token: string | null;
  role: "stakeholder" | "requirements_engineer" | null;
  setToken: (token: string | null) => void;
  setRole: (role: "stakeholder" | "requirements_engineer" | null) => void;
  clear: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      setToken: (token) => set({ token }),
      setRole: (role) => set({ role }),
      clear: () => set({ token: null, role: null }),
    }),
    { name: "probing-auth" }
  )
);
