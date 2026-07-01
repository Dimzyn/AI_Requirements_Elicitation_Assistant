import { describe, expect, it } from "vitest";
import { resolutionLabel } from "./resolutionLabel";

describe("resolutionLabel", () => {
  it("labels each decision", () => {
    expect(resolutionLabel("a_wins")).toBe("Prioritize the first requirement");
    expect(resolutionLabel("b_wins")).toBe("Prioritize the second requirement");
    expect(resolutionLabel("compromise")).toBe("Compromise");
    expect(resolutionLabel("restate")).toBe("Restated requirement");
  });

  it("falls back for an unknown decision", () => {
    expect(resolutionLabel("something_else")).toBe("Resolution recorded");
  });
});
