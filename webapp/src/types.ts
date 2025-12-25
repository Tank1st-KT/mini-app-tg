export type AuthResponse = {
  ok: boolean;
  token: string;
  user: { telegram_id: number };
};

export type GenerateResponse = {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  echo_prompt?: string;
  result_text?: string;
};

export type Job = {
  id: string;
  status: string;
  prompt: string;
  created_at: string;
  result_text?: string;
};
