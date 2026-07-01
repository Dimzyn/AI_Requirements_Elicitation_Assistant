import { describe, expect, it } from "vitest";
import { conflictsByRequirementId } from "./conflictMap";
import type { Conflict } from "../../api/conflicts";

const conflict = (id: string, reqAId: string, reqBId: string): Conflict => ({
  id,
  project_id: "p1",
  status: "open",
  explanation: `why-${id}`,
  requirement_a: { id: reqAId, statement: `a-${reqAId}`, stakeholder: "Alice" },
  requirement_b: { id: reqBId, statement: `b-${reqBId}`, stakeholder: "Bob" },
  resolution_sessions: [],
  proposal: null,
  votes: [],
  resolutions: [],
  detected_at: "2026-01-01T00:00:00Z",
});

describe("conflictsByRequirementId", () => {
  it("maps both sides of each conflict to that conflict", () => {
    const c = conflict("c1", "r1", "r2");
    const m = conflictsByRequirementId([c]);
    expect(m.get("r1")).toBe(c);
    expect(m.get("r2")).toBe(c);
    expect(m.size).toBe(2);
  });

  it("indexes multiple conflicts and ignores unrelated requirement ids", () => {
    const m = conflictsByRequirementId([conflict("c1", "r1", "r2"), conflict("c2", "r3", "r4")]);
    expect([...m.keys()].sort()).toEqual(["r1", "r2", "r3", "r4"]);
    expect(m.get("r1")?.id).toBe("c1");
    expect(m.get("r4")?.id).toBe("c2");
    expect(m.has("r99")).toBe(false);
  });

  it("returns an empty map for no conflicts", () => {
    expect(conflictsByRequirementId([]).size).toBe(0);
  });
});
