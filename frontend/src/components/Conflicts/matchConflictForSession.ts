import type { Conflict } from "../../api/conflicts";

export function matchConflictForSession(
  conflicts: Conflict[],
  sessionId: string
): Conflict | null {
  return (
    conflicts.find((c) => c.resolution_sessions.some((rs) => rs.id === sessionId)) ?? null
  );
}
