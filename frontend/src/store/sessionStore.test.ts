import { beforeEach, describe, expect, it } from "vitest";
import { useSessionStore } from "./sessionStore";
import type { Requirement, Turn } from "../api/sessions";

const turn = (id: string, role: Turn["role"] = "agent"): Turn => ({
  id,
  role,
  content: `c-${id}`,
  created_at: "2026-01-01T00:00:00Z",
});

const requirement = (id: string): Requirement => ({
  id,
  statement: `r-${id}`,
  type: "functional",
  source_turn_id: "t1",
  created_at: "2026-01-01T00:00:00Z",
});

// Zustand stores are module singletons, so reset to a known baseline per test.
const reset = () =>
  useSessionStore.setState({
    sessions: [],
    activeId: null,
    skipNextTurnLoad: false,
    turns: [],
    requirements: [],
    status: "idle",
  });

describe("sessionStore", () => {
  beforeEach(reset);

  describe("setActive", () => {
    it("switching to a different session resets turns, requirements and status", () => {
      useSessionStore.setState({
        activeId: "s1",
        turns: [turn("a")],
        requirements: [requirement("r")],
        status: "validating",
      });

      useSessionStore.getState().setActive("s2");

      const s = useSessionStore.getState();
      expect(s.activeId).toBe("s2");
      expect(s.turns).toEqual([]);
      expect(s.requirements).toEqual([]);
      expect(s.status).toBe("idle");
    });

    it("re-selecting the current session does not reset turns", () => {
      const turns = [turn("greeting"), turn("question")];
      useSessionStore.setState({ activeId: "s1", turns });

      useSessionStore.getState().setActive("s1");

      const s = useSessionStore.getState();
      expect(s.activeId).toBe("s1");
      expect(s.turns).toBe(turns); // untouched reference
    });
  });

  describe("appendTurns", () => {
    it("appends in order after existing turns", () => {
      useSessionStore.setState({ turns: [turn("1")] });

      useSessionStore.getState().appendTurns([turn("2"), turn("3")]);

      expect(useSessionStore.getState().turns.map((t) => t.id)).toEqual(["1", "2", "3"]);
    });
  });
});
