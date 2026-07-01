import { api } from "./client";

export type InvitationView = { email: string; project_title: string; status: string };

export const viewInvitation = (token: string) =>
  api.get<InvitationView>(`/invitations/${token}`).then((r) => r.data);

export const acceptInvitation = (
  token: string,
  password: string,
  real_name?: string,
  job_title?: string
) =>
  api
    .post<{ access_token: string }>(`/invitations/${token}/accept`, {
      password,
      real_name,
      job_title,
    })
    .then((r) => r.data.access_token);
