import { api } from "./client";

export type SreRequirement = {
  id: string;
  session_id: string;
  statement: string;
  type: "functional" | "non_functional" | "constraint";
  source_turn_id: string;
  priority: string | null;
  status: string | null;
  acceptance_criteria: string | null;
  edited_by: string | null;
  edited_at: string | null;
  created_at: string;
};

export type RequirementPatch = {
  statement?: string;
  type?: string;
  priority?: string;
  status?: string;
  acceptance_criteria?: string;
};

export const listAllRequirements = (params?: {
  session_id?: string;
  status?: string;
  type?: string;
}) => api.get<SreRequirement[]>("/requirements", { params }).then((r) => r.data);

export const patchRequirement = (id: string, body: RequirementPatch) =>
  api.patch<SreRequirement>(`/requirements/${id}`, body).then((r) => r.data);
