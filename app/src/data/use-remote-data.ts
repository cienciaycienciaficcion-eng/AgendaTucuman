import { useCallback, useEffect, useState } from 'react';
import {
  fallbackAgendaEvents,
  fallbackCinemaData,
  RADIO_STREAM_URL,
  RADIO_PLAYER_URL,
  fallbackMovieInfoData,
} from '@/data';
import {
  fetchRemoteAgenda,
  fetchRemoteCinema,
  fetchRemoteRadio,
  fetchRemoteMovies,
} from './remote';

export function useAgendaData() {
  const [events, setEvents] = useState<any[]>(fallbackAgendaEvents);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchRemoteAgenda();
      if (!Array.isArray(data)) throw new Error('Agenda remota inválida');
      setEvents(data);
      setOnline(true);
      setUpdatedAt(new Date().toISOString());
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return { events, loading, online, updatedAt, refresh };
}

export function useCinemaData() {
  const [data, setData] = useState<any>(fallbackCinemaData);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await fetchRemoteCinema();
      if (!next?.cartelera?.movies || !Array.isArray(next.cartelera.movies)) {
        throw new Error('Cartelera remota inválida');
      }
      setData(next);
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

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
      if (!next || (!next.stream_urls?.length && !next.audio_urls?.length && !next.player?.player_url)) {
        throw new Error('Radio remota inválida');
      }
      setData(next);
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const stream =
    data?.stream_urls?.[0] ||
    data?.audio_urls?.[0] ||
    RADIO_STREAM_URL;

  const player =
    data?.player?.player_url ||
    RADIO_PLAYER_URL;

  return { data, stream, player, loading, online, refresh };
}


export function useMovieInfoData() {
  const [data, setData] = useState<any>(fallbackMovieInfoData);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await fetchRemoteMovies();
      if (!next?.peliculas || !Array.isArray(next.peliculas)) {
        throw new Error('Información de películas remota inválida');
      }
      setData(next);
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return { data, loading, online, refresh };
}
