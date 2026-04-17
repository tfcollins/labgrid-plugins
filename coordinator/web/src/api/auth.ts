const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export interface AuthUser {
  username: string;
  role: "admin" | "user";
}

export interface ManagedUser {
  id: number;
  username: string;
  role: "admin" | "user";
  disabled: boolean;
  has_password: boolean;
  has_oidc: boolean;
}

export const authApi = {
  me: () => request<AuthUser>("/auth/me"),
  login: (username: string, password: string) =>
    request<AuthUser>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  bootstrap: (token: string, username: string, password: string) =>
    request<AuthUser>("/auth/bootstrap", {
      method: "POST",
      body: JSON.stringify({ token, username, password }),
    }),
  oidcLoginUrl: () => `${API_BASE}/auth/oidc/login`,

  listUsers: () => request<ManagedUser[]>("/users"),
  createUser: (username: string, password: string | null, role: "admin" | "user") =>
    request<ManagedUser>("/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    }),
  deleteUser: (id: number) =>
    request<void>(`/users/${id}`, { method: "DELETE" }),
  setPassword: (id: number, password: string) =>
    request<void>(`/users/${id}/password`, {
      method: "PUT",
      body: JSON.stringify({ password }),
    }),
  setRole: (id: number, role: "admin" | "user") =>
    request<void>(`/users/${id}/role`, {
      method: "PUT",
      body: JSON.stringify({ role }),
    }),
  setDisabled: (id: number, disabled: boolean) =>
    request<void>(`/users/${id}/disabled`, {
      method: "PUT",
      body: JSON.stringify({ disabled }),
    }),
};
