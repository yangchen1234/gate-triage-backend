import type { Job, ModelStatus, Port, Snapshot } from './types.ts';

const TOKEN_STORAGE = 'gate-triage-console-token';
let token = '';
try { token = sessionStorage.getItem(TOKEN_STORAGE) || ''; } catch { /* Session still works without browser storage. */ }

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const requestToken = token;
  const headers = new Headers(init.headers);
  if (token) headers.set('X-Console-Token', token);
  if (init.body) headers.set('Content-Type', 'application/json');
  let response: Response;
  try { response = await fetch(`/api/console${path}`, { ...init, headers, credentials: 'same-origin', signal: init.signal || AbortSignal.timeout(15000) }); }
  catch { if (token !== requestToken) throw new ApiError(-1, 'Previous session response discarded.'); throw new ApiError(0, 'Connection interrupted or timed out. Check the connection, then try again.'); }
  const data = await response.json().catch(() => null);
  if (token !== requestToken && !(path === '/session' && init.method === 'POST')) throw new ApiError(-1, 'Previous session response discarded.');
  if (!response.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : undefined;
    throw new ApiError(response.status, response.status === 401 ? 'Your preview session has expired. Start a new session and reconnect Claude to continue.' :
      response.status === 409 || response.status === 412 ? detail || 'The queue changed. Refresh its current state, then generate a new plan.' :
      detail || `Request failed (${response.status}). Please try again.`);
  }
  return data as T;
}

export async function newSession(): Promise<Snapshot> {
  const data = await request<Snapshot & { token: string }>('/session', { method: 'POST' });
  token = data.token;
  try { sessionStorage.setItem(TOKEN_STORAGE, token); } catch { /* No key is ever stored here. */ }
  bootstrap = Promise.resolve(data);
  return data;
}

let bootstrap: Promise<Snapshot> | null = null;
export function loadSession(): Promise<Snapshot> {
  // Shared across React StrictMode's initial effects: never create duplicate sessions.
  if (!bootstrap) {
    const pending = token ? request<Snapshot>('/session') : newSession();
    const shared = pending.catch(error => { if (bootstrap === shared) bootstrap = null; throw error; });
    bootstrap = shared;
  }
  return bootstrap;
}

// A scoped session capability, never the provider API key.
export const consoleSessionHeaders = (): Record<string,string> => token ? { 'X-Console-Token': token } : {};

export const api = {
  session: () => request<Snapshot>('/session'),
  ports: () => request<{ ports: Port[]; tariff_notice: string }>('/ports'),
  scenario: (patch: object, revision: number) => request<Snapshot>('/scenario', { method: 'POST', headers: { 'If-Match': String(revision) }, body: JSON.stringify(patch) }),
  configure: async (api_key: string, model: string) => (await request<{ model: ModelStatus }>('/agent/config', { method: 'PUT', body: JSON.stringify({ api_key, model }) })).model,
  connectTeam: async (access_code: string) => (await request<{ model: ModelStatus }>('/agent/team', { method: 'PUT', body: JSON.stringify({ access_code }) })).model,
  disconnect: async () => (await request<{ model: ModelStatus }>('/agent/config', { method: 'DELETE' })).model,
  plans: () => request<{ plans: Job[] }>('/plans'),
  plan: (id: string) => request<Job>(`/plans/${encodeURIComponent(id)}`),
  generate: (body: { top_n: number; use_model: boolean }, revision: number, key: string) => request<Job>('/plans', { method: 'POST', headers: { 'If-Match': String(revision), 'Idempotency-Key': key }, body: JSON.stringify(body) }),
  decide: (id: string, body: object, revision: number) => request<Job>(`/plans/${encodeURIComponent(id)}/decisions`, { method: 'POST', headers: { 'If-Match': String(revision) }, body: JSON.stringify(body) }),
};
