import agendaData from './agenda_tucuman.json';
import cinemaData from './cine_cinemacenter_tucuman.json';

export const fallbackAgendaEvents: any[] = Array.isArray(agendaData)
  ? agendaData
  : Array.isArray((agendaData as any)?.events)
    ? (agendaData as any).events
    : Array.isArray((agendaData as any)?.data)
      ? (agendaData as any).data
      : [];

export const fallbackCinemaData: any = cinemaData;

export const RADIO_STREAM_URL =
  'https://streaming01.shockmedia.com.ar:10693/stream';

export const RADIO_PLAYER_URL =
  'https://streaming01.shockmedia.com.ar/cp/widgets/player/single/?p=8718';

export const todayIso = () => {
  const d = new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
};

export const formatDate = (value: string) => {
  if (!value) return '';
  const d = new Date(`${value}T12:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('es-AR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

export type AgendaEvent = {
  id: string;
  title: string;
  url: string;
  date_start: string;
  date_end: string;
  time_start: string;
  time_end: string;
  start_datetime: string;
  end_datetime: string;
  description: string;
  image: string;
  price: number | null;
  currency: string;
  is_free: boolean;
  location: string;
  address: string;
  city: string;
  organizer: string;
  categories: string[];
  tags: string[];
  map_search_url: string;
  registration_urls: string[];
  external_urls: string[];
  occurrences: Array<{
    date: string;
    time_start: string;
    time_end: string;
    start_datetime: string;
    end_datetime: string;
  }>;
};

export type CinemaMovie = {
  id: string;
  title: string;
  status: string;
  format: string;
  language: string;
  week_start: string;
  week_end: string;
  schedule: Record<string, string[]>;
  occurrences: Array<{
    date: string;
    time: string;
    datetime: string;
    weekday: string;
  }>;
};

export type CinemaData = {
  cinema: {
    name: string;
    address: string;
    city: string;
    country: string;
  };
  cartelera: {
    week_start: string | null;
    week_end: string | null;
    movies: CinemaMovie[];
  };
};
