import { beforeEach, describe, expect, it, vi } from "vitest";

// authStore uses zustand's persist middleware (localStorage). The node test env
// has no localStorage, so provide a minimal in-memory shim BEFORE the store loads.
vi.hoisted(() => {
  if (typeof (globalThis as { localStorage?: Storage }).localStorage === "undefined") {
    const store = new Map<string, string>();
    (globalThis as { localStorage?: Storage }).localStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      key: () => null,
      length: 0,
    } as Storage;
  }
});

import { logout, resetUserScopedStores } from "./authActions";
import { useAuthStore } from "./authStore";
import { useSessionStore } from "./sessionStore";
import { useSpecStore } from "./specStore";

describe("authActions", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, role: null });
    useSessionStore.getState().reset();
    useSpecStore.getState().reset();
  });

  it("resetUserScopedStores wipes session + spec data but keeps the auth token", () => {
    useAuthStore.setState({ token: "tok", role: "stakeholder" });
    useSessionStore.setState({
      activeId: "s1",
      turns: [{ id: "a", role: "agent", content: "hi", created_at: "x" }],
    });
    useSpecStore.setState({ selectedId: "r1", filterStatus: "approved" });

    resetUserScopedStores();

    expect(useSessionStore.getState().activeId).toBeNull();
    expect(useSessionStore.getState().turns).toEqual([]);
    expect(useSpecStore.getState().selectedId).toBeNull();
    expect(useSpecStore.getState().filterStatus).toBeNull();
    expect(useAuthStore.getState().token).toBe("tok"); // identity untouched
  });

  it("logout clears the auth identity and all user-scoped state", () => {
    useAuthStore.setState({ token: "tok", role: "requirements_engineer" });
    useSessionStore.setState({
      activeId: "s9",
      turns: [{ id: "z", role: "stakeholder", content: "c", created_at: "x" }],
    });

    logout();

    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().role).toBeNull();
    expect(useSessionStore.getState().activeId).toBeNull();
    expect(useSessionStore.getState().turns).toEqual([]);
  });
});
