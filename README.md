# Agenda Tucumán — Cinemacenter Metadata V4

Reemplazar en el repositorio:

- `scripts/enrich-cinemacenter-metadata.py`
- `.github/workflows/enrich-cine-metadata.yml`

Esta versión reconstruye `cine_metadata.json` en cada ejecución exclusivamente desde Cinemacenter.

No usa TMDB, IMDb, Google, La Nación ni metadata histórica para completar películas.

La coincidencia de fichas es estricta: el título completo debe corresponder con el título de la ficha. Esto evita falsos positivos como `VERTIGO 2` -> `U2: Vertigo`.

Si una ficha no se encuentra o le faltan datos, la película permanece en cartelera con `metadata_status: partial` y los campos faltantes se informan en `metadata_missing`.

El workflow ya no necesita `TMDB_API_TOKEN` ni instala `requests`.

## Ejecución

GitHub → Actions → Actualizar metadata de cine → Run workflow.

Revisar el bloque `RESUMEN DE METADATA CINEMACENTER`.
