import { describe, expect, it } from "vitest";
import { voteSummary } from "./voteSummary";
import type { ResolutionVote } from "../../api/conflicts";

const vote = (choice: ResolutionVote["choice"]): ResolutionVote => ({
  stakeholder: "Alice",
  choice,
  comment: null,
  voted_at: "2026-01-01T00:00:00Z",
});

describe("voteSummary", () => {
  it("returns 'No votes yet' when empty", () => {
    expect(voteSummary([])).toBe("No votes yet");
  });

  it("counts accepts and change requests", () => {
    expect(voteSummary([vote("accept"), vote("request_changes")])).toBe(
      "1 accepted, 1 requested changes"
    );
  });

  it("omits a zero bucket", () => {
    expect(voteSummary([vote("accept"), vote("accept")])).toBe("2 accepted");
  });
});
