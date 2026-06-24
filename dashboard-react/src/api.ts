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
    // Redirect to root instead of reloading to avoid infinite reload loops
    // when the API keeps returning 401
    if (!sessionStorage.getItem('vtx_auth_redirect')) {
      sessionStorage.setItem('vtx_auth_redirect', '1');
      window.location.replace('/dashboard');
    }
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

/** Download a file from an authenticated endpoint (sends the dashboard key, then saves the blob). */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const res = await fetch(path, { headers: { 'X-Dashboard-Key': getApiKey() } });
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
