import type { ResolutionVote } from "../../api/conflicts";

export function voteSummary(votes: ResolutionVote[]): string {
  if (votes.length === 0) return "No votes yet";
  const accepted = votes.filter((v) => v.choice === "accept").length;
  const changes = votes.filter((v) => v.choice === "request_changes").length;
  const parts: string[] = [];
  if (accepted) parts.push(`${accepted} accepted`);
  if (changes) parts.push(`${changes} requested changes`);
  return parts.join(", ");
}
