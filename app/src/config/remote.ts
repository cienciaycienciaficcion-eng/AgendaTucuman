/**
 * URL base de los datos publicados por GitHub.
 *
 * Cambiá GITHUB_RAW_BASE cuando crees/subas el repositorio.
 * Ejemplo:
 * https://raw.githubusercontent.com/usuario/agenda-tucuman/main/datos
 */
export const GITHUB_RAW_BASE =
  'https://raw.githubusercontent.com/cienciaycienciaficcion-eng/AgendaTucuman/main/datos';

export const REMOTE_DATA_URLS = {
  agenda: `${GITHUB_RAW_BASE}/agenda_eventos.json`,
  cinema: `${GITHUB_RAW_BASE}/cine_cinemacenter_tucuman.json`,
  radio: `${GITHUB_RAW_BASE}/radio_tucuman.json`,
};

export const REMOTE_TIMEOUT_MS = 10000;
