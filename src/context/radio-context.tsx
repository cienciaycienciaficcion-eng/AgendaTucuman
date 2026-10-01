import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useAudioPlayer, useAudioPlayerStatus, setAudioModeAsync } from 'expo-audio';
import { useRadioData } from '@/data/use-remote-data';

type RadioTrack = {
  title: string;
  artist: string;
  raw?: string;
};

type RadioContextValue = {
  playing: boolean;
  loading: boolean;
  online: boolean;
  stream: string;
  currentTrack: RadioTrack | null;
  play: () => void;
  pause: () => void;
  stop: () => void;
};

const RadioContext = createContext<RadioContextValue | null>(null);

const DEFAULT_TRACK: RadioTrack = {
  title: 'Agenda Tucumán',
  artist: 'Radio en vivo',
};

const METADATA_URLS = [
  'https://streaming01.shockmedia.com.ar:10693/7.html',
  'https://streaming01.shockmedia.com.ar:10693/currentsong',
  'https://streaming01.shockmedia.com.ar:10693/status-json.xsl',
  'https://streaming01.shockmedia.com.ar:10693/statistics?sid=1&json=1',
];

function cleanTrackText(value: unknown) {
  return String(value ?? '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function parseTrack(value: any): RadioTrack | null {
  if (!value) return null;

  if (typeof value === 'string') {
    const text = cleanTrackText(value);
    if (!text || /^(agenda tucum[aá]n|radio en vivo|stream)$/i.test(text)) return null;

    // SHOUTcast 7.html can return "status,listeners,songtitle".
    const shoutcastFields = text.split(',').map(part => part.trim()).filter(Boolean);
    if (shoutcastFields.length >= 3 && /^\d+$/.test(shoutcastFields[0])) {
      const song = shoutcastFields.slice(2).join(', ');
      return parseTrack(song);
    }

    // SHOUTcast/Centova often sends "Artist - Title".
    const parts = text.split(/\s+-\s+/);
    if (parts.length >= 2) {
      return { artist: parts.shift()!.trim(), title: parts.join(' - ').trim(), raw: text };
    }
    return { artist: '', title: text, raw: text };
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const parsed = parseTrack(item);
      if (parsed) return parsed;
    }
    return null;
  }

  if (typeof value === 'object') {
    const title = cleanTrackText(
      value.title ??
      value.songtitle ??
      value.songTitle ??
      value.current_song ??
      value.currentSong ??
      value.now_playing ??
      value.nowPlaying ??
      value.streamtitle ??
      value.streamTitle
    );
    const artist = cleanTrackText(value.artist ?? value.artist_name ?? value.artistName ?? value.dj);

    if (title || artist) {
      return {
        title: title || 'Radio en vivo',
        artist,
        raw: [artist, title].filter(Boolean).join(' - '),
      };
    }

    for (const key of ['song', 'songtitle', 'now_playing', 'nowPlaying', 'current', 'current_song', 'data', 'response', 'icestats', 'songhistory']) {
      const parsed = parseTrack(value[key]);
      if (parsed) return parsed;
    }
  }

  return null;
}

async function fetchRadioMetadata(): Promise<RadioTrack | null> {
  for (const url of METADATA_URLS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(`${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`, {
        headers: { Accept: 'application/json,text/html,text/plain,*/*' },
        signal: controller.signal,
        cache: 'no-store',
      });
      if (!response.ok) continue;

      const text = await response.text();
      if (!text) continue;

      try {
        const json = JSON.parse(text);
        const parsed = parseTrack(json);
        if (parsed) return parsed;
      } catch {
        const parsed = parseTrack(text);
        if (parsed) return parsed;
      }
    } catch {
      // Try the next metadata endpoint.
    } finally {
      clearTimeout(timer);
    }
  }

  return null;
}

export function RadioProvider({ children }: { children: React.ReactNode }) {
  const { data: radioData, stream, online, loading } = useRadioData();
  const player = useAudioPlayer(stream, {
    updateInterval: 1000,
    preferredForwardBufferDuration: 15,
  });
  const status = useAudioPlayerStatus(player);
  const [currentTrack, setCurrentTrack] = useState<RadioTrack | null>(() => parseTrack(radioData));

  useEffect(() => {
    void setAudioModeAsync({
      playsInSilentMode: true,
      shouldPlayInBackground: true,
      interruptionMode: 'doNotMix',
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      const track = await fetchRadioMetadata();
      if (!cancelled && track) {
        setCurrentTrack(previous => {
          if (previous?.raw === track.raw) return previous;
          return track;
        });
      }
    };

    void poll();
    const interval = setInterval(() => { void poll(); }, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [radioData]);

  useEffect(() => {
    const remoteTrack = parseTrack(radioData);
    if (remoteTrack) setCurrentTrack(remoteTrack);
  }, [radioData]);

  useEffect(() => {
    if (!currentTrack) return;

    try {
      player.updateLockScreenMetadata?.({
        title: currentTrack.title || DEFAULT_TRACK.title,
        artist: currentTrack.artist || DEFAULT_TRACK.artist,
        albumTitle: 'Agenda Tucumán Radio',
        artworkUrl: 'https://agendatucuman.com.ar/wp-content/uploads/2026/05/banner-2-1024x244.png',
      });
    } catch {
      // Lock-screen metadata is optional.
    }
  }, [currentTrack, player]);

  const play = () => {
    const track = currentTrack ?? DEFAULT_TRACK;
    player.setActiveForLockScreen(true, {
      title: track.title,
      artist: track.artist || DEFAULT_TRACK.artist,
      albumTitle: 'Agenda Tucumán Radio',
      artworkUrl: 'https://agendatucuman.com.ar/wp-content/uploads/2026/05/banner-2-1024x244.png',
    }, { isLiveStream: true, showSeekBackward: false, showSeekForward: false });
    player.play();
  };

  const pause = () => player.pause();

  const stop = () => {
    player.pause();
    player.clearLockScreenControls();
  };

  const value = useMemo(() => ({
    playing: Boolean(status.playing),
    loading,
    online,
    stream,
    currentTrack,
    play,
    pause,
    stop,
  }), [status.playing, loading, online, stream, currentTrack]);

  return <RadioContext.Provider value={value}>{children}</RadioContext.Provider>;
}

export function useRadioPlayer() {
  const context = useContext(RadioContext);
  if (!context) throw new Error('useRadioPlayer debe usarse dentro de RadioProvider');
  return context;
}
