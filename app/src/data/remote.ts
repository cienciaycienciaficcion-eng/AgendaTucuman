import { REMOTE_DATA_URLS, REMOTE_TIMEOUT_MS } from '@/config/remote';

async function fetchJson<T>(url: string): Promise<T> {
  const controller = typeof AbortController !== 'undefined'
    ? new AbortController()
    : undefined;

  const timer = controller
    ? setTimeout(() => controller.abort(), REMOTE_TIMEOUT_MS)
    : undefined;

  try {
    const separator = url.includes('?') ? '&' : '?';
    const response = await fetch(`${url}${separator}t=${Date.now()}`, {
      headers: { Accept: 'application/json' },
      signal: controller?.signal,
      cache: 'no-store',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json() as T;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function fetchRemoteAgenda(): Promise<any[]> {
  const data = await fetchJson<any>(REMOTE_DATA_URLS.agenda);
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.events)) return data.events;
  if (Array.isArray(data?.data)) return data.data;
  throw new Error('Formato de agenda no reconocido');
}

export async function fetchRemoteCinema(): Promise<any> {
  return fetchJson<any>(REMOTE_DATA_URLS.cinema);
}

export async function fetchRemoteRadio(): Promise<any> {
  return fetchJson<any>(REMOTE_DATA_URLS.radio);
}
