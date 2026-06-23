import { useAuthStore } from "./authStore";
import { useSessionStore } from "./sessionStore";
import { useSpecStore } from "./specStore";

/**
 * Wipe all user-scoped client state (sessions, chat turns, requirements,
 * selections, filters). The auth token is persisted, but these stores live only
 * in memory — without this, one account's chat history bleeds into the next when
 * switching accounts in the same tab (a client-side nav, not a full reload).
 */
export function resetUserScopedStores() {
  useSessionStore.getState().reset();
  useSpecStore.getState().reset();
}

/** Full logout: clear auth identity and every user-scoped store. */
export function logout() {
  useAuthStore.getState().clear();
  resetUserScopedStores();
}
