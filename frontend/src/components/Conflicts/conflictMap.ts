import type { Conflict } from "../../api/conflicts";

/**
 * Index every conflicted requirement id to the conflict it belongs to, so a
 * requirements-list row can flag itself. Both sides of each conflict are mapped.
 * Pure helper (mirrors `contactMessage.ts`) so it can be unit-tested in the node env.
 */
export function conflictsByRequirementId(conflicts: Conflict[]): Map<string, Conflict> {
  const m = new Map<string, Conflict>();
  for (const c of conflicts) {
    m.set(c.requirement_a.id, c);
    m.set(c.requirement_b.id, c);
  }
  return m;
}
