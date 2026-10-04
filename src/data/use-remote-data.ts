import { AppState } from 'react-native';
import { useCallback, useEffect, useState } from 'react';
import {
  fallbackAgendaEvents,
  isServiceEvent,
  fallbackCinemaData,
  RADIO_STREAM_URL,
  RADIO_PLAYER_URL,
  fallbackCinemaMetadata,
  normalizeSearchText,
} from '@/data';
import {
  fetchRemoteAgenda,
  fetchRemoteServices,
  fetchRemoteCinema,
  fetchRemoteCinemaMetadata,
  fetchRemoteRadio,
} from './remote';

const AGENDA_CHECK_INTERVAL_MS = 8 * 60 * 60 * 1000;
let agendaLastServerCheck = 0;
let agendaRefreshPromise: Promise<any[]> | null = null;

async function refreshAgendaOnce() {
  if (agendaRefreshPromise) return agendaRefreshPromise;
  agendaRefreshPromise = fetchRemoteAgenda()
    .then(data => {
      if (!Array.isArray(data)) throw new Error('Agenda remota inválida');
      agendaLastServerCheck = Date.now();
      return data;
    })
    .finally(() => { agendaRefreshPromise = null; });
  return agendaRefreshPromise;
}


const SERVICES_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
let servicesLastServerCheck = 0;
let servicesRefreshPromise: Promise<any[]> | null = null;

async function refreshServicesOnce() {
  if (servicesRefreshPromise) return servicesRefreshPromise;
  servicesRefreshPromise = fetchRemoteServices()
    .then(data => {
      if (!Array.isArray(data)) throw new Error('Servicios remotos inválidos');
      servicesLastServerCheck = Date.now();
      return data;
    })
    .finally(() => { servicesRefreshPromise = null; });
  return servicesRefreshPromise;
}

export function useServicesData() {
  const fallback = fallbackAgendaEvents.filter(isServiceEvent);
  const [events, setEvents] = useState<any[]>(fallback);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await refreshServicesOnce();
      const remoteServices = data.map((event: any) =>
        isServiceEvent(event)
          ? event
          : {
              ...event,
              categories: [
                ...(Array.isArray(event.categories) ? event.categories : []),
                'Servicios',
              ],
            }
      );

      // La fuente dedicada de Servicios y la agenda histórica pueden contener
      // publicaciones distintas. Las combinamos para no perder servicios si
      // una de las dos fuentes todavía no fue actualizada.
      const merged = [...remoteServices, ...fallback];
      const seen = new Set<string>();
      const unique = merged.filter((event: any) => {
        const key = String(event.id || event.url || event.title || '').trim().toLowerCase();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      });

      setEvents(unique);
      setOnline(true);
    } catch {
      // El extractor dedicado puede no existir todavía: en ese caso
      // usamos los Servicios que ya vengan dentro de agenda_eventos.json.
      setEvents(fallback);
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, [fallback.length]);

  useEffect(() => {
    void refresh();
    const subscription = AppState.addEventListener('change', nextState => {
      if (nextState === 'active' && Date.now() - servicesLastServerCheck >= SERVICES_CHECK_INTERVAL_MS) {
        void refresh();
      }
    });
    return () => subscription.remove();
  }, [refresh]);

  return { events, loading, online, refresh };
}

export function useAgendaData() {
  const [events, setEvents] = useState<any[]>(fallbackAgendaEvents);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await refreshAgendaOnce();
      setEvents(data);
      setOnline(true);
      setUpdatedAt(new Date().toISOString());
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Primera apertura: actualizar automáticamente sin mostrar un botón de actualización.
    void refresh();

    const subscription = AppState.addEventListener('change', nextState => {
      if (nextState === 'active' && Date.now() - agendaLastServerCheck >= AGENDA_CHECK_INTERVAL_MS) {
        void refresh();
      }
    });

    return () => subscription.remove();
  }, [refresh]);

  return { events, loading, online, updatedAt, refresh };
}


function mergeCinemaMetadata(data: any, remoteMetadata: any[] = []) {
  if (!data || typeof data !== 'object') return data;

  const findMetadata = (items: any[], title: string) =>
    items.find((item: any) => {
      const candidates = [
        ...(Array.isArray(item?.match) ? item.match : []),
        item?.title,
        item?.original_title,
      ].filter(Boolean);
      return candidates.some((matchTitle: string) =>
        normalizeSearchText(matchTitle) === normalizeSearchText(title)
      );
    });

  const mergeMovie = (movie: any) => {
    const localMetadata = findMetadata(fallbackCinemaMetadata, movie.title);
    const currentRemoteMetadata = findMetadata(remoteMetadata, movie.title);

    return {
      ...movie,
      metadata: {
        ...(localMetadata ?? {}),
        ...(currentRemoteMetadata ?? {}),
        ...(movie.metadata ?? {}),
      },
    };
  };

  return {
    ...data,
    ...(data.cartelera && Array.isArray(data.cartelera.movies)
      ? {
          cartelera: {
            ...data.cartelera,
            movies: data.cartelera.movies.map(mergeMovie),
          },
        }
      : {}),
    ...(Array.isArray(data.proximos_estrenos)
      ? {
          proximos_estrenos: data.proximos_estrenos.map(mergeMovie),
        }
      : {}),
  };
}


const CINEMA_CHECK_INTERVAL_MS = 60 * 60 * 1000;
let cinemaLastServerCheck = 0;

export function useCinemaData() {
  const [data, setData] = useState<any>(mergeCinemaMetadata(fallbackCinemaData));
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await fetchRemoteCinema();

      let remoteMetadata: any[] = [];
      try {
        const metadataData = await fetchRemoteCinemaMetadata();
        if (Array.isArray(metadataData?.movies)) {
          remoteMetadata = metadataData.movies;
        }
      } catch {
        // La cartelera sigue siendo utilizable aunque el archivo de
        // metadata no esté disponible temporalmente.
      }

      // Cinemacenter puede responder temporalmente con una lista vacía de
      // próximos estrenos aunque la cartelera semanal sea válida. En ese caso
      // nunca reemplazamos una lista local válida por [].
      const remoteUpcoming = Array.isArray(next?.proximos_estrenos)
        ? next.proximos_estrenos
        : [];
      const bundledUpcoming = Array.isArray(fallbackCinemaData?.proximos_estrenos)
        ? fallbackCinemaData.proximos_estrenos
        : [];

      let cinemaToMerge = next;
      if (remoteUpcoming.length === 0 && bundledUpcoming.length > 0) {
        cinemaToMerge = {
          ...next,
          proximos_estrenos: bundledUpcoming,
        };
      }

      const merged = mergeCinemaMetadata(cinemaToMerge, remoteMetadata);
      setData(merged);
      setOnline(true);
      cinemaLastServerCheck = Date.now();
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();

    const subscription = AppState.addEventListener('change', nextState => {
      if (
        nextState === 'active' &&
        Date.now() - cinemaLastServerCheck >= CINEMA_CHECK_INTERVAL_MS
      ) {
        void refresh();
      }
    });

    return () => subscription.remove();
  }, [refresh]);

  return { data, loading, online, refresh };
}

export function useRadioData() {
  const [data, setData] = useState<any>({
    stream_urls: [RADIO_STREAM_URL],
    audio_urls: [RADIO_STREAM_URL],
    player: { player_url: RADIO_PLAYER_URL },
  });
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await fetchRemoteRadio();
      if (!next || (!next.stream_urls?.length && !next.audio_urls?.length && !next.player?.player_url)) throw new Error('Radio remota inválida');
      setData(next);
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const stream = data?.stream_urls?.[0] || data?.audio_urls?.[0] || RADIO_STREAM_URL;
  const player = data?.player?.player_url || RADIO_PLAYER_URL;
  return { data, stream, player, loading, online, refresh };
}
