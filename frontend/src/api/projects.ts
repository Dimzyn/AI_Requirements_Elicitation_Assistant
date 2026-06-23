import { api } from "./client";

export type Project = {
  id: string;
  title: string;
  background?: string | null;
  goals?: string | null;
  scope?: string | null;
  created_at?: string | null;
};

export type Member = {
  user_id: string;
  email: string;
  real_name: string;
  joined_at?: string | null;
};

export type Invite = {
  id: string;
  email: string;
  status: string;
  token: string;
  accept_url: string;
  expires_at?: string | null;
};

export type ProjectSession = {
  id: string;
  project_id: string;
  stakeholder_id: string;
  title?: string | null;
  kind?: string;
  conflict_id?: string | null;
  status: string;
  phase: string;
  stakeholder_finished?: boolean;
  created_at?: string | null;
  stakeholder_name?: string | null;
  stakeholder_email?: string | null;
};

export const listProjects = () => api.get<Project[]>("/projects").then((r) => r.data);
export const getProject = (id: string) => api.get<Project>(`/projects/${id}`).then((r) => r.data);
export const createProject = (body: Partial<Project> & { title: string }) =>
  api.post<Project>("/projects", body).then((r) => r.data);
export const inviteStakeholder = (pid: string, email: string) =>
  api.post<Invite>(`/projects/${pid}/invitations`, { email }).then((r) => r.data);
export const listMembers = (pid: string) =>
  api.get<Member[]>(`/projects/${pid}/members`).then((r) => r.data);
export const listProjectSessions = (pid: string) =>
  api.get<ProjectSession[]>(`/projects/${pid}/sessions`).then((r) => r.data);
export const completeSession = (sid: string) =>
  api.post<ProjectSession>(`/sessions/${sid}/complete`).then((r) => r.data);
export const myMemberProjects = () =>
  api.get<Project[]>("/projects/mine/memberships").then((r) => r.data);
export const exportProjectSrs = (pid: string, format: "md" | "txt" | "pdf" = "md") =>
  api
    .get(`/projects/${pid}/export`, { params: { format }, responseType: "blob" })
    .then((r) => r.data as Blob);
