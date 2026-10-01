# Agenda Tucumán

## Actualización de datos

Los datos se actualizan mediante `.github/workflows/actualizar_datos.yml`.

### Cinemacenter

La cartelera y la metadata de películas se obtienen en **una única ejecución** desde Cinemacenter.

El extractor `extractores/cinemacenter.py`:

1. descarga la cartelera oficial semanal de Tucumán;
2. obtiene los `movieId` internos desde `seleccionarMovie(...)`;
3. consulta `ajax_movieSlider.php` con ese `movieId`;
4. sigue el enlace `/ficha/{movieId}-...` entregado por Cinemacenter;
5. extrae la metadata de esa ficha;
6. usa como `release_date` la primera fecha de aparición de la película en la cartelera semanal de Tucumán;
7. extrae el tráiler solamente si Cinemacenter lo publica en la ficha;
8. obtiene también los próximos estrenos desde la página oficial `/estrenos` y guarda el enlace oficial de Mi Boletería (`https://www.miboleteria.com.ar`);
9. genera `cine_cinemacenter_tucuman.json` y `cine_metadata.json`.

No se utilizan TMDB, IMDb, Google, Jina ni coincidencias externas para la metadata de Cinemacenter.

Si Cinemacenter no publica un dato, el campo queda vacío/null. Los valores obviamente inválidos publicados por el sitio (por ejemplo, 31/12/1969 como fecha) no se convierten en datos de película.

### Archivos publicados

- `datos/cine_cinemacenter_tucuman.json`
- `datos/cine_metadata.json`
- `src/data/cine_cinemacenter_tucuman.json`
- `src/data/cine_metadata.json`

## Prueba local del mecanismo de Cinemacenter

Desde la raíz del repositorio:

```bat
python extractores\cinemacenter.py --test-ids 5786,5808,5800,5801
```

Esta prueba consulta directamente los `movieId` de Cinemacenter y no modifica los JSON. El `movieId=5786` fue comprobado durante el desarrollo; los demás IDs deben verificarse contra la cartelera vigente antes de tomarlos como referencia.

Para ejecutar la actualización completa:

```bat
python extractores\cinemacenter.py
```
