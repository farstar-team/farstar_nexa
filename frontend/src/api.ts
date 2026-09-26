export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
  ) {
    super(code);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const csrf =
    document.cookie
      .split("; ")
      .find((item) => item.startsWith("nexa_csrf="))
      ?.split("=")[1] ?? "";
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new ApiError(
      typeof data.detail === "string" ? data.detail : "error",
      response.status,
    );
  return data as T;
}
export type User = {
  id: string;
  username: string;
  email: string;
  role: "USER" | "ADMIN" | "SUPER_ADMIN";
  active: boolean;
  timezone: string;
};
export type Config = {
  mock_mode: boolean;
  registration_enabled: boolean;
  google_login_enabled?: boolean;
  version: string;
};
export type Account = {
  id: string;
  name: string;
  provider: string;
  active: boolean;
};
export type Rule = {
  status: string;
  trigger_type: string;
  product_id: string | null;
  scope: string;
  media_ids: string[];
  flow: { version?: number; actions?: import("./commerce").Action[] };
  id: string;
  account_id: string;
  name: string;
  enabled: boolean;
  keywords: string[];
  match_mode: string;
  response: string;
  priority: number;
  cooldown_seconds: number;
};
export type Conversation = {
  id: string;
  account_id: string;
  sender_id: string;
  created_at: string;
};
export type Message = {
  id: string;
  direction: string;
  text: string;
  status: string;
  created_at: string;
};
export type Execution = {
  dry_run: boolean;
  trigger: string;
  automation_name: string;
  product_name: string | null;
  media_caption: string | null;
  actions: string[];
  id: string;
  automation_id: string;
  status: string;
  detail: string;
  created_at: string;
};
export type Activity = {
  id: string;
  action: string;
  target: string;
  created_at: string;
};
export type Operation = {
  id: string;
  action: string;
  status: string;
  stage: string;
  result?: { latest?: string; status?: string };
  error?: string;
};
export type Backup = {
  name: string;
  size: number;
  version: string;
  status: string;
  created_at: string;
};
