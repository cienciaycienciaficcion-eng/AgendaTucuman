import { AppState } from 'react-native';
import { useCallback, useEffect, useState } from 'react';
import {
  fallbackAgendaEvents,
  fallbackCinemaData,
  RADIO_STREAM_URL,
  RADIO_PLAYER_URL,
  fallbackCinemaMetadata,
  normalizeSearchText,
} from '@/data';
import {
  fetchRemoteAgenda,
  fetchRemoteCinema,
  fetchRemoteRadio,
} from './remote';

const AGENDA_CHECK_INTERVAL_MS = 8 * 60 * 60 * 1000;
const CINEMA_CHECK_INTERVAL_MS = 15 * 60 * 1000;
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


function mergeCinemaMetadata(data: any) {
  // Cinemacenter es la única fuente de metadata. No mezclamos con la copia
  // histórica/bundled porque podría reintroducir posters o datos de terceros.
  return data;
}

let cinemaLastServerCheck = 0;
let cinemaRefreshPromise: Promise<any> | null = null;

async function refreshCinemaOnce() {
  if (cinemaRefreshPromise) return cinemaRefreshPromise;
  cinemaRefreshPromise = fetchRemoteCinema()
    .then(next => {
      if (!next?.cartelera?.movies || !Array.isArray(next.cartelera.movies)) {
        throw new Error('Cartelera remota inválida');
      }
      cinemaLastServerCheck = Date.now();
      return next;
    })
    .finally(() => { cinemaRefreshPromise = null; });
  return cinemaRefreshPromise;
}

export function useCinemaData() {
  const [data, setData] = useState<any>(mergeCinemaMetadata(fallbackCinemaData));
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await refreshCinemaOnce();
      const merged = mergeCinemaMetadata(next);
      setData(merged);
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();

    const interval = setInterval(() => {
      if (Date.now() - cinemaLastServerCheck >= CINEMA_CHECK_INTERVAL_MS) {
        void refresh();
      }
    }, 60 * 1000);

    const subscription = AppState.addEventListener('change', nextState => {
      if (nextState === 'active' && Date.now() - cinemaLastServerCheck >= CINEMA_CHECK_INTERVAL_MS) {
        void refresh();
      }
    });

    return () => {
      clearInterval(interval);
      subscription.remove();
    };
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
