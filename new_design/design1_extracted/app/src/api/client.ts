const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function handleAuth(status: number) {
  if (status === 401 || status === 403) {
    window.location.href = '/';
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  if (USE_MOCK) {
    const { mockApiGet } = await import('./__mocks__');
    return mockApiGet(path) as Promise<T>;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
  });
  handleAuth(res.status);
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return res.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  if (USE_MOCK) {
    const { mockApiPost } = await import('./__mocks__');
    return mockApiPost(path, body) as Promise<T>;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });
  handleAuth(res.status);
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return res.json();
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  if (USE_MOCK) {
    const { mockApiPut } = await import('./__mocks__');
    return mockApiPut(path, body) as Promise<T>;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });
  handleAuth(res.status);
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return res.json();
}
