# Fix GitHub: metadata faltante de Cinemacenter

Este parche NO modifica la app Expo.

## Archivos

- `.github/workflows/actualizar_datos.yml`
  - después de Cinemacenter intenta completar los campos faltantes con TMDB.
  - conserva los datos ya obtenidos por Cinemacenter.
  - obtiene la clasificación argentina desde TMDB cuando está disponible.
  - sigue ejecutándose automáticamente cada 6 horas.
- `.github/workflows/enrich-cine-metadata.yml`
  - workflow manual para volver a intentar el enriquecimiento.
- `scripts/enrich-cine-metadata-fallback.py`
  - resuelve películas que Cinemacenter dejó incompletas.
  - agrega `metadata_status`, `metadata_missing`, `sources_checked`.
  - elimina de `cine_metadata.json` las películas que ya no están en la cartelera actual.
  - si una película vuelve a cartelera, vuelve a resolverla.

## Secret requerido

Usa el mismo secret que ya utiliza el proyecto:

`TMDB_API_TOKEN`

No se agrega ningún secret nuevo.

## Orden de fuentes

1. Cinemacenter: fuente principal.
2. TMDB: solo completa campos que siguen vacíos.
3. Clasificación: se toma de la certificación de Argentina de TMDB cuando existe.

No se inventan valores.
