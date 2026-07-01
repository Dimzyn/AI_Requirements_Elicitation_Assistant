import { describe, expect, it } from "vitest";
import { matchConflictForSession } from "./matchConflictForSession";
import type { Conflict } from "../../api/conflicts";

const conflict = (id: string, sessionIds: string[]): Conflict => ({
  id,
  project_id: "p",
  status: "open",
  explanation: "e",
  requirement_a: { id: "a", statement: "A", stakeholder: null },
  requirement_b: { id: "b", statement: "B", stakeholder: null },
  resolution_sessions: sessionIds.map((sid) => ({ id: sid, stakeholder: null })),
  proposal: null,
  votes: [],
  resolutions: [],
  detected_at: "2026-01-01T00:00:00Z",
});

describe("matchConflictForSession", () => {
  it("finds the conflict whose resolution sessions include the id", () => {
    const conflicts = [conflict("c1", ["s1", "s2"]), conflict("c2", ["s3"])];
    expect(matchConflictForSession(conflicts, "s3")?.id).toBe("c2");
  });

  it("returns null when no conflict matches", () => {
    expect(matchConflictForSession([conflict("c1", ["s1"])], "sX")).toBeNull();
  });
});
