let csrf = '';
export function setCsrf(token: string) { csrf = token; }

export async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (data !== undefined) headers['Content-Type'] = 'application/json';
  if (!['GET', 'HEAD'].includes(method) && csrf) headers['X-CSRF-Token'] = csrf;
  const response = await fetch(`/api${path}`, {
    method, headers, credentials: 'include',
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  let payload: any = null;
  try { payload = await response.json(); } catch { /* non-json gateway failure */ }
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload as T;
}
