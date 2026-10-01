import agendaData from './agenda_tucuman.json';
import cinemaData from './cine_cinemacenter_tucuman.json';
import cinemaMetadata from './cine_metadata.json';

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


export const eventEffectiveEndDate = (event: any): string => {
  const dates = [
    typeof event?.date_end === 'string' ? event.date_end : '',
    ...(Array.isArray(event?.occurrences)
      ? event.occurrences.map((o: any) => typeof o?.date === 'string' ? o.date : '')
      : []),
  ].filter(Boolean);
  return dates.sort().at(-1) ?? '';
};

export const eventIsActiveOrUpcoming = (event: any, date = todayIso()) => {
  const end = eventEffectiveEndDate(event);
  return Boolean(end && end >= date);
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

export type CinemaMovieMetadata = {
  title: string;
  original_title?: string;
  year?: number;
  release_date?: string;
  duration_minutes?: number;
  genres?: string[];
  director?: string[];
  cast?: string[];
  synopsis?: string;
  poster?: string;
  imdb_id?: string;
  imdb_url?: string;
  source_url?: string;
  trailer?: string;
  nationality?: string;
  classification?: string;
  /** @deprecated kept for backward compatibility with older metadata */
  rating?: string;
  distributor?: string;
};

export type CinemaMovie = {
  id: string;
  title: string;
  metadata?: CinemaMovieMetadata;
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
  proximos_estrenos?: Array<{
    id: string;
    title: string;
    release_date?: string | null;
    source_url?: string;
    source?: string;
  }>;
  mi_boleteria_url?: string;
};


export const fallbackCinemaMetadata: any[] = Array.isArray((cinemaMetadata as any)?.movies)
  ? (cinemaMetadata as any).movies
  : [];

export function normalizeSearchText(value: unknown): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function eventCategories(event: any): string[] {
  if (Array.isArray(event?.categories)) return event.categories.map(String);
  if (Array.isArray(event?.category_names)) return event.category_names.map(String);
  if (typeof event?.category === 'string') return [event.category];
  return [];
}

export function isServiceEvent(event: any): boolean {
  return eventCategories(event).some(category => {
    const key = normalizeSearchText(category);
    return key === 'servicios' || key === 'servicio' || key.includes('servicio');
  });
}
