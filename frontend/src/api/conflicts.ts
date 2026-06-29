import { api } from "./client";

export type RequirementRef = {
  id: string;
  statement: string;
  stakeholder: string | null;
};

export type ResolutionSessionRef = {
  id: string;
  stakeholder: string | null;
};

export type ResolutionProposal = {
  statement: string;
  rationale: string | null;
  published_at: string;
};

export type ResolutionVote = {
  stakeholder: string | null;
  choice: "accept" | "request_changes";
  comment: string | null;
  voted_at: string;
};

export type Conflict = {
  id: string;
  project_id: string;
  status: "open" | "resolved" | "dismissed";
  explanation: string;
  requirement_a: RequirementRef;
  requirement_b: RequirementRef;
  resolution_sessions: ResolutionSessionRef[];
  proposal: ResolutionProposal | null;
  votes: ResolutionVote[];
  detected_at: string;
};

export const detectConflicts = (projectId: string) =>
  api.post<Conflict[]>(`/projects/${projectId}/conflicts/detect`).then((r) => r.data);

export const listConflicts = (projectId: string, status?: string) =>
  api
    .get<Conflict[]>(`/projects/${projectId}/conflicts`, { params: status ? { status } : undefined })
    .then((r) => r.data);

export const updateConflict = (id: string, status: "resolved" | "dismissed") =>
  api.patch<Conflict>(`/conflicts/${id}`, { status }).then((r) => r.data);

export type ResolutionSuggestion = {
  suggestion: string;
  rationale: string;
};

export const suggestResolution = (conflictId: string) =>
  api.post<ResolutionSuggestion>(`/conflicts/${conflictId}/suggest`).then((r) => r.data);

export const proposeResolution = (cid: string, statement: string, rationale?: string | null) =>
  api.post<Conflict>(`/conflicts/${cid}/propose`, { statement, rationale }).then((r) => r.data);

export const applyResolution = (
  cid: string,
  survivingRequirementId: string,
  statement: string
) =>
  api
    .post<{ id: string; status: string }>(`/conflicts/${cid}/apply`, {
      surviving_requirement_id: survivingRequirementId,
      statement,
    })
    .then((r) => r.data);

export type ResolutionCard = {
  proposal: ResolutionProposal | null;
  my_vote: ResolutionVote | null;
};

export const getResolutionCard = (sessionId: string) =>
  api.get<ResolutionCard>(`/sessions/${sessionId}/resolution`).then((r) => r.data);

export const voteResolution = (
  sessionId: string,
  choice: "accept" | "request_changes",
  comment?: string
) =>
  api
    .post<ResolutionCard>(`/sessions/${sessionId}/vote`, { choice, comment })
    .then((r) => r.data);
