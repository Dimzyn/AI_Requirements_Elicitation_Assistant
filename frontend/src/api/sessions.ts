import { api } from "./client";

export type Session = { id: string; project_title: string; status: string; phase: string };
export type Turn = {
  id: string;
  role: "stakeholder" | "agent";
  content: string;
  strategy?: string | null;
  created_at: string;
};
export type Requirement = {
  id: string;
  statement: string;
  type: "functional" | "non_functional" | "constraint";
  source_turn_id: string;
  created_at: string;
};
export type PostTurnResponse = {
  stakeholder_turn_id: string;
  questions: { id: string; content: string; strategy: string }[];
};

export const listSessions = () => api.get<Session[]>("/sessions").then((r) => r.data);
export const createSession = (project_title?: string) =>
  api.post<Session>("/sessions", project_title ? { project_title } : {}).then((r) => r.data);
export const archiveSession = (id: string) =>
  api.post<Session>(`/sessions/${id}/archive`).then((r) => r.data);
export const unarchiveSession = (id: string) =>
  api.post<Session>(`/sessions/${id}/unarchive`).then((r) => r.data);
export const deleteSession = (id: string) =>
  api.delete<void>(`/sessions/${id}`).then((r) => r.data);
export const getTurns = (id: string) => api.get<Turn[]>(`/sessions/${id}/turns`).then((r) => r.data);
export const postTurn = (id: string, content: string, count = 5) =>
  api.post<PostTurnResponse>(`/sessions/${id}/turns`, { content }, { params: { count } }).then((r) => r.data);
export const postMessage = (id: string, content: string) =>
  api
    .post<{ stakeholder_turn_id: string; session_title?: string | null }>(
      `/sessions/${id}/messages`,
      { content }
    )
    .then((r) => r.data);
export const postQuestion = (id: string) =>
  api.post<{ id: string; content: string; strategy: string }>(`/sessions/${id}/questions`).then((r) => r.data);
export const getRequirements = (id: string) =>
  api.get<Requirement[]>(`/sessions/${id}/requirements`).then((r) => r.data);
export const exportSession = (id: string, format: "md" | "txt" = "md") =>
  api
    .get(`/sessions/${id}/export`, { params: { format }, responseType: "blob" })
    .then((r) => r.data as Blob);
