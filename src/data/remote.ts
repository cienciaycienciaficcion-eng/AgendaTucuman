import {
  REMOTE_DATA_URLS,
  REMOTE_DATA_FALLBACK_URLS,
  REMOTE_TIMEOUT_MS,
} from '@/config/remote';

async function fetchJson<T>(url: string): Promise<T> {
  const controller = typeof AbortController !== 'undefined'
    ? new AbortController()
    : undefined;

  const timer = controller
    ? setTimeout(() => controller.abort(), REMOTE_TIMEOUT_MS)
    : undefined;

  try {
    // Cache-busting explícito: la cartelera cambia semanalmente y no
    // queremos que el navegador reutilice una copia vieja.
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

async function fetchWithFallback<T>(
  primaryUrl: string,
  fallbackUrl: string,
  validate?: (data: T) => boolean,
): Promise<T> {
  let lastError: unknown = null;

  for (const url of [primaryUrl, fallbackUrl]) {
    try {
      const data = await fetchJson<T>(url);
      if (validate && !validate(data)) {
        throw new Error('Datos remotos inválidos');
      }
      return data;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error('No se pudo obtener el recurso remoto');
}

function localTodayIso(): string {
  const d = new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function isCurrentCinemaData(data: any): boolean {
  if (!data?.cartelera || !Array.isArray(data.cartelera.movies)) return false;

  const weekEnd = typeof data.cartelera.week_end === 'string'
    ? data.cartelera.week_end
    : '';

  // Si el servidor devuelve una cartelera vencida, no la aceptamos:
  // permite que jsDelivr actúe como respaldo antes de caer al JSON local.
  return !weekEnd || weekEnd >= localTodayIso();
}

export async function fetchRemoteAgenda(): Promise<any[]> {
  const data = await fetchWithFallback<any>(
    REMOTE_DATA_URLS.agenda,
    REMOTE_DATA_FALLBACK_URLS.agenda,
    value =>
      Array.isArray(value) ||
      Array.isArray(value?.events) ||
      Array.isArray(value?.data),
  );

  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.events)) return data.events;
  if (Array.isArray(data?.data)) return data.data;
  throw new Error('Formato de agenda no reconocido');
}

export async function fetchRemoteServices(): Promise<any[]> {
  return fetchWithFallback<any>(
    REMOTE_DATA_URLS.services,
    REMOTE_DATA_FALLBACK_URLS.services,
    value => Array.isArray(value) || Array.isArray(value?.events) || Array.isArray(value?.data),
  ).then(data => {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.events)) return data.events;
    if (Array.isArray(data?.data)) return data.data;
    throw new Error('Formato de servicios no reconocido');
  });
}

export async function fetchRemoteCinema(): Promise<any> {
  return fetchWithFallback<any>(
    REMOTE_DATA_URLS.cinema,
    REMOTE_DATA_FALLBACK_URLS.cinema,
    isCurrentCinemaData,
  );
}

export async function fetchRemoteCinemaMetadata(): Promise<any> {
  return fetchWithFallback<any>(
    REMOTE_DATA_URLS.cinemaMetadata,
    REMOTE_DATA_FALLBACK_URLS.cinemaMetadata,
    value => Array.isArray(value?.movies),
  );
}

export async function fetchRemoteRadio(): Promise<any> {
  return fetchWithFallback<any>(
    REMOTE_DATA_URLS.radio,
    REMOTE_DATA_FALLBACK_URLS.radio,
    value => Boolean(
      value &&
      (value.stream_urls?.length ||
        value.audio_urls?.length ||
        value.player?.player_url),
    ),
  );
}
