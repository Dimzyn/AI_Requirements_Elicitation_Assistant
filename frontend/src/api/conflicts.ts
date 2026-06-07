import { api } from "./client";

export type RequirementRef = {
  id: string;
  statement: string;
  stakeholder: string | null;
};

export type Conflict = {
  id: string;
  project_id: string;
  status: "open" | "resolved" | "dismissed";
  explanation: string;
  requirement_a: RequirementRef;
  requirement_b: RequirementRef;
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
