/**
 * Fuentes remotas de datos de Agenda Tucumán.
 *
 * GitHub Raw es la fuente principal. jsDelivr funciona como respaldo
 * para evitar que una incidencia temporal de raw.githubusercontent.com
 * deje a la aplicación usando silenciosamente datos locales vencidos.
 */
export const GITHUB_RAW_BASE =
  'https://raw.githubusercontent.com/cienciaycienciaficcion-eng/AgendaTucuman/main/datos';

export const GITHUB_CDN_BASE =
  'https://cdn.jsdelivr.net/gh/cienciaycienciaficcion-eng/AgendaTucuman@main/datos';

export const REMOTE_DATA_URLS = {
  agenda: `${GITHUB_RAW_BASE}/agenda_eventos.json`,
  services: `${GITHUB_RAW_BASE}/servicios_tucuman.json`,
  cinema: `${GITHUB_RAW_BASE}/cine_cinemacenter_tucuman.json`,
  cinemaMetadata: `${GITHUB_RAW_BASE}/cine_metadata.json`,
  radio: `${GITHUB_RAW_BASE}/radio_tucuman.json`,
};

export const REMOTE_DATA_FALLBACK_URLS = {
  agenda: `${GITHUB_CDN_BASE}/agenda_eventos.json`,
  services: `${GITHUB_CDN_BASE}/servicios_tucuman.json`,
  cinema: `${GITHUB_CDN_BASE}/cine_cinemacenter_tucuman.json`,
  cinemaMetadata: `${GITHUB_CDN_BASE}/cine_metadata.json`,
  radio: `${GITHUB_CDN_BASE}/radio_tucuman.json`,
};

export const REMOTE_TIMEOUT_MS = 10000;
