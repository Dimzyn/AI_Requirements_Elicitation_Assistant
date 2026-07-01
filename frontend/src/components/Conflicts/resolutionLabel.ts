export function resolutionLabel(decision: string): string {
  switch (decision) {
    case "a_wins":
      return "Prioritize the first requirement";
    case "b_wins":
      return "Prioritize the second requirement";
    case "compromise":
      return "Compromise";
    case "restate":
      return "Restated requirement";
    default:
      return "Resolution recorded";
  }
}
