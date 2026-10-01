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
  classification?: string;
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
};
