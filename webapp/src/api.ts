import type { AuthResponse, GenerateResponse, Job } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export async function authTelegram(initData: string): Promise<AuthResponse> {
  const r = await fetch(`${API_BASE}/auth/telegram`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initData })
  });
  if (!r.ok) throw new Error("Auth failed");
  return r.json();
}

export async function createGeneration(token: string, prompt: string): Promise<GenerateResponse> {
  const r = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ prompt })
  });
  if (!r.ok) throw new Error("Generate failed");
  return r.json();
}

/**
 * История задач. Если у вас пока нет /jobs — вернём пусто без падения UI.
 */
export async function listJobs(token: string): Promise<Job[]> {
  const r = await fetch(`${API_BASE}/jobs`, {
    headers: { ...authHeaders(token) }
  });

  if (r.status === 404) return [];
  if (!r.ok) throw new Error("Jobs failed");
  return r.json();
}

/**
 * Создание платежа (заглушка). Ожидается, что бэкенд вернёт url для редиректа.
 */
export async function createPayment(token: string, productId: string): Promise<{ url: string }> {
  const r = await fetch(`${API_BASE}/payments/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ productId })
  });
  if (!r.ok) throw new Error("Payment create failed");
  return r.json();
}
