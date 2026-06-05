import { api } from "./client";

export type SignupPayload = {
  email: string;
  password: string;
  real_name: string;
  phone?: string;
};

export type UserProfile = {
  id: string;
  email: string;
  real_name: string;
  role: "stakeholder" | "requirements_engineer";
};

export const signup = (body: SignupPayload) =>
  api.post("/auth/signup", body).then((r) => r.data.access_token as string);

export const login = (body: { email: string; password: string }) =>
  api.post("/auth/login", body).then((r) => r.data.access_token as string);

export const getMe = () => api.get<UserProfile>("/auth/me").then((r) => r.data);
