function greeting(name: string | null): string {
  const trimmed = (name ?? "").trim();
  return trimmed.length > 0 ? trimmed : "there";
}

function projectLabel(title: string): string {
  const trimmed = (title ?? "").trim();
  return trimmed.length > 0 ? trimmed : "this project";
}

export function buildContactMessage(args: {
  stakeholderName: string | null;
  theirStatement: string;
  otherStatement: string;
  explanation: string;
  projectTitle: string;
}): string {
  const { stakeholderName, theirStatement, otherStatement, explanation, projectTitle } = args;
  return [
    `Hi ${greeting(stakeholderName)},`,
    ``,
    `While reviewing requirements for ${projectLabel(projectTitle)}, one of your requirements appears to conflict with another stakeholder's:`,
    ``,
    `• Your requirement: "${theirStatement}"`,
    `• Conflicting requirement: "${otherStatement}"`,
    ``,
    `Why they conflict: ${explanation}`,
    ``,
    `Could you let us know how you'd like to resolve this?`,
  ].join("\n");
}

export function buildSelfContactMessage(args: {
  stakeholderName: string | null;
  statementA: string;
  statementB: string;
  explanation: string;
  projectTitle: string;
}): string {
  const { stakeholderName, statementA, statementB, explanation, projectTitle } = args;
  return [
    `Hi ${greeting(stakeholderName)},`,
    ``,
    `While reviewing requirements for ${projectLabel(projectTitle)}, two of your requirements appear to contradict each other:`,
    ``,
    `• "${statementA}"`,
    `• "${statementB}"`,
    ``,
    `Why they conflict: ${explanation}`,
    ``,
    `Could you let us know how you'd like to reconcile these?`,
  ].join("\n");
}
