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


export type MovieTrailer = {
  id?: string;
  titulo: string;
  tipo: string;
  youtube_id: string;
  url: string;
  oficial?: boolean;
};

export type MovieInfo = {
  id: string;
  titulo: string;
  titulo_original: string;
  anio: number | null;
  fecha_estreno: string | null;
  duracion_minutos: number | null;
  generos: string[];
  director: string[];
  actores: Array<{
    nombre: string;
    personaje: string;
  }>;
  sinopsis: string;
  poster: string | null;
  trailers: MovieTrailer[];
  tmdb_id: number | null;
  tmdb_url: string | null;
  fuente: string | null;
  titulo_cinemacenter: string;
  actualizado_at: string;
};

export type MovieInfoData = {
  schema_version: string;
  generated_at: string;
  source: {
    metadata: string;
    cinema: string;
    tmdb_api: string;
    attribution_required: boolean;
    attribution_notice: string;
  };
  cinema_reference: {
    week_start: string | null;
    week_end: string | null;
  };
  peliculas: MovieInfo[];
  summary: {
    total: number;
    resueltas_tmdb: number;
    sinopsis_disponibles: number;
    posters_disponibles: number;
    trailers_disponibles: number;
    sin_resolver: string[];
  };
};
