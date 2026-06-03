import { beforeEach, describe, expect, it } from "vitest";
import { useSpecStore } from "./specStore";
import type { SreRequirement } from "../api/requirements";

const req = (id: string, over: Partial<SreRequirement> = {}): SreRequirement => ({
  id,
  session_id: "sess-1",
  statement: `statement-${id}`,
  type: "functional",
  source_turn_id: "t1",
  priority: null,
  status: "pending",
  acceptance_criteria: null,
  edited_by: null,
  edited_at: null,
  created_at: "2026-01-01T00:00:00Z",
  ...over,
});

const reset = () =>
  useSpecStore.setState({
    sessions: [],
    requirements: [],
    selectedId: null,
    filterSessionId: null,
    filterStatus: null,
    filterType: null,
  });

describe("specStore", () => {
  beforeEach(reset);

  describe("updateRequirement", () => {
    it("replaces only the matching requirement, by id", () => {
      useSpecStore.setState({ requirements: [req("a"), req("b"), req("c")] });

      useSpecStore.getState().updateRequirement(req("b", { status: "approved", priority: "must" }));

      const reqs = useSpecStore.getState().requirements;
      expect(reqs.map((r) => r.id)).toEqual(["a", "b", "c"]); // order preserved
      expect(reqs.find((r) => r.id === "b")?.status).toBe("approved");
      expect(reqs.find((r) => r.id === "b")?.priority).toBe("must");
      // siblings untouched
      expect(reqs.find((r) => r.id === "a")?.status).toBe("pending");
    });

    it("is a no-op when no id matches", () => {
      const original = [req("a"), req("b")];
      useSpecStore.setState({ requirements: original });

      useSpecStore.getState().updateRequirement(req("zzz", { status: "rejected" }));

      const reqs = useSpecStore.getState().requirements;
      expect(reqs.map((r) => r.id)).toEqual(["a", "b"]);
      expect(reqs.every((r) => r.status === "pending")).toBe(true);
    });
  });

  describe("filters", () => {
    it("set and clear independently", () => {
      const s = useSpecStore.getState();
      s.setFilterSessionId("sess-9");
      s.setFilterStatus("approved");
      s.setFilterType("non_functional");

      let cur = useSpecStore.getState();
      expect(cur.filterSessionId).toBe("sess-9");
      expect(cur.filterStatus).toBe("approved");
      expect(cur.filterType).toBe("non_functional");

      cur.setFilterStatus(null);
      cur = useSpecStore.getState();
      expect(cur.filterStatus).toBeNull();
      // other filters remain
      expect(cur.filterSessionId).toBe("sess-9");
      expect(cur.filterType).toBe("non_functional");
    });
  });
});
