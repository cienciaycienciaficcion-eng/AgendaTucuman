import { useCallback, useEffect, useState } from 'react';
import {
  fallbackAgendaEvents,
  fallbackCinemaData,
  RADIO_STREAM_URL,
  RADIO_PLAYER_URL,
} from '@/data';
import {
  fetchRemoteAgenda,
  fetchRemoteCinema,
  fetchRemoteRadio,
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
      setData(await fetchRemoteCinema());
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
      setData(await fetchRemoteRadio());
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
