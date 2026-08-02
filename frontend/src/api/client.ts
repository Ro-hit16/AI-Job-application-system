// src/api/client.ts
import axios from "axios";

const BASE_URL = "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Inject JWT token on every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Redirect to login on 401
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// ─── Auth ─────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post("/auth/login", new URLSearchParams({ username: email, password }), {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }),
  register: (data: { email: string; full_name: string; password: string }) =>
    apiClient.post("/auth/register", data),
  me: () => apiClient.get("/auth/me"),
};

// ─── Resumes ──────────────────────────────────────────────────────────────────
export const resumesApi = {
  list: () => apiClient.get("/resumes/"),
  upload: (file: File, setPrimary = true) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiClient.post(`/resumes/upload?set_primary=${setPrimary}`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  delete: (id: string) => apiClient.delete(`/resumes/${id}`),
};

// ─── Jobs ─────────────────────────────────────────────────────────────────────
export const jobsApi = {
  list: (params?: { portal?: string; status?: string; search?: string; limit?: number; offset?: number }) =>
    apiClient.get("/jobs/", { params }),
  get: (id: string) => apiClient.get(`/jobs/${id}`),
};

// ─── Applications ─────────────────────────────────────────────────────────────
export const applicationsApi = {
  list: (status?: string) => apiClient.get("/applications/", { params: status ? { status } : {} }),
  pending: () => apiClient.get("/applications/pending"),
  get: (id: string) => apiClient.get(`/applications/${id}`),
  approve: (id: string, decision: string, edit_instructions?: string) =>
    apiClient.post(`/applications/${id}/approve`, { decision, edit_instructions }),
};

// ─── Agents ───────────────────────────────────────────────────────────────────
export const agentsApi = {
  run: (data: { resume_id: string; portals?: string[]; match_threshold?: number }) =>
    apiClient.post("/agents/run", data),
  status: (runId: string) => apiClient.get(`/agents/status/${runId}`),
};

// ─── Notifications ────────────────────────────────────────────────────────────
export const notificationsApi = {
  list: (unreadOnly = false) => apiClient.get("/notifications/", { params: { unread_only: unreadOnly } }),
  markRead: (id: string) => apiClient.patch(`/notifications/${id}/read`),
  markAllRead: () => apiClient.patch("/notifications/read-all"),
};

export const interviewApi = {
  start: (data: {
    job_id?: string;
    job_title?: string;
    company?: string;
    job_description?: string;
    technical_questions?: number;
    hr_questions?: number;
    resume_id?: string;
  }) => apiClient.post("/interview/start", data),
  answer: (session_id: string, answer: string) =>
    apiClient.post("/interview/answer", { session_id, answer }),
  report: (session_id: string) => apiClient.get(`/interview/report/${session_id}`),
  session: (session_id: string) => apiClient.get(`/interview/session/${session_id}`),
  end: (session_id: string) => apiClient.delete(`/interview/session/${session_id}`),
  jobs: () => apiClient.get("/interview/jobs/list"),
};