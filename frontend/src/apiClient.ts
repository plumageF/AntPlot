export const API_BASE = "http://127.0.0.1:8765";

export type ApiResponse<T> = {
  ok: boolean;
  data: T;
  errors: Array<{ code: string; message: string; severity?: "error" | "warning" | "info"; context?: Record<string, unknown> }>;
  warnings: Array<{ code: string; message: string; severity?: "error" | "warning" | "info"; context?: Record<string, unknown> }>;
  infos: Array<{ code: string; message: string; severity?: "error" | "warning" | "info"; context?: Record<string, unknown> }>;
};

function createSessionId() {
  const existing = window.sessionStorage.getItem("hfss_paperplotter_session_id");
  if (existing) return existing;
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `session_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  window.sessionStorage.setItem("hfss_paperplotter_session_id", random);
  return random;
}

export const clientSessionId = createSessionId();

export function fileUrl(path: string | null) {
  return path ? `${API_BASE}/file?path=${encodeURIComponent(path)}&t=${Date.now()}` : null;
}

export async function callApi<T>(action: string, payload: Record<string, unknown>): Promise<ApiResponse<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, session_id: clientSessionId })
    });
  } catch (error) {
    throw new Error(`Backend connection failed while calling ${action}. Please make sure the Python backend is running at ${API_BASE}. ${error instanceof Error ? error.message : String(error)}`);
  }
  const result = await response.json();
  if (!response.ok || !result.ok) {
    throw new Error((result.errors || []).map((item: { message: string }) => item.message).join("\n") || result.error || `${action} failed`);
  }
  return result;
}
