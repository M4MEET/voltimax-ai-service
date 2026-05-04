const API_KEY_STORAGE = 'vtx_api_key';

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) || '';
}

export function setApiKey(key: string) {
  localStorage.setItem(API_KEY_STORAGE, key);
}

export function clearApiKey() {
  localStorage.removeItem(API_KEY_STORAGE);
}

export async function apiFetch<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'X-Dashboard-Key': getApiKey(),
      ...init?.headers,
    },
  });
  if (res.status === 401) {
    clearApiKey();
    window.location.reload();
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function adminFetch<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}
