import { api } from "./client";

export type Session = {
  id: string;
  project_id: string;
  stakeholder_id: string;
  title?: string | null;
  status: string;
  phase: string;
  created_at?: string | null;
};
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

export const openProjectSession = (pid: string) =>
  api.post<Session>(`/projects/${pid}/session`).then((r) => r.data);
