import { describe, expect, it } from "vitest";
import { buildContactMessage, buildSelfContactMessage } from "./contactMessage";

describe("buildContactMessage", () => {
  it("includes the stakeholder's own statement, the conflicting one, and the explanation", () => {
    const msg = buildContactMessage({
      stakeholderName: "Alice",
      theirStatement: "Auto-approve all refunds.",
      otherStatement: "All refunds require manager sign-off.",
      explanation: "Cannot both auto-approve and require sign-off.",
      projectTitle: "Refund System",
    });
    expect(msg).toContain("Hi Alice,");
    expect(msg).toContain("Refund System");
    expect(msg).toContain('Your requirement: "Auto-approve all refunds."');
    expect(msg).toContain('Conflicting requirement: "All refunds require manager sign-off."');
    expect(msg).toContain("Why they conflict: Cannot both auto-approve and require sign-off.");
  });

  it("swaps roles correctly for the second stakeholder", () => {
    // For stakeholder B, their own statement leads and the other's is the conflicting one.
    const msg = buildContactMessage({
      stakeholderName: "Bob",
      theirStatement: "All refunds require manager sign-off.",
      otherStatement: "Auto-approve all refunds.",
      explanation: "Cannot both auto-approve and require sign-off.",
      projectTitle: "Refund System",
    });
    expect(msg).toContain('Your requirement: "All refunds require manager sign-off."');
    expect(msg).toContain('Conflicting requirement: "Auto-approve all refunds."');
  });

  it("falls back to 'there' when the name is missing", () => {
    const msg = buildContactMessage({
      stakeholderName: null,
      theirStatement: "A",
      otherStatement: "B",
      explanation: "x",
      projectTitle: "P",
    });
    expect(msg).toContain("Hi there,");
  });

  it("falls back to 'this project' when the title is empty", () => {
    const msg = buildContactMessage({
      stakeholderName: "Bob",
      theirStatement: "A",
      otherStatement: "B",
      explanation: "x",
      projectTitle: "",
    });
    expect(msg).toContain("requirements for this project,");
  });
});

describe("buildSelfContactMessage", () => {
  it("lists both of the stakeholder's statements once and asks to reconcile", () => {
    const msg = buildSelfContactMessage({
      stakeholderName: "Carol",
      statementA: "Export to PDF.",
      statementB: "Never store documents.",
      explanation: "Exporting requires temporarily storing the document.",
      projectTitle: "Docs App",
    });
    expect(msg).toContain("Hi Carol,");
    expect(msg).toContain("two of your requirements");
    expect(msg).toContain('"Export to PDF."');
    expect(msg).toContain('"Never store documents."');
    expect(msg).toContain("Why they conflict: Exporting requires temporarily storing the document.");
    expect(msg).toContain("reconcile these?");
  });

  it("falls back to 'there' when the name is missing", () => {
    const msg = buildSelfContactMessage({
      stakeholderName: null,
      statementA: "A",
      statementB: "B",
      explanation: "x",
      projectTitle: "P",
    });
    expect(msg).toContain("Hi there,");
  });
});
