# Configuración de GitHub

El repositorio configurado para la app es:

`https://github.com/cienciaycienciaficcion-eng/AgendaTucuman`

## 1. Subir el proyecto

Subí el contenido de este ZIP al repositorio `AgendaTucuman`.

La estructura debe quedar así:

```text
AgendaTucuman/
├── app/
├── extractores/
├── datos/
├── .github/
├── README.md
└── GITHUB_SETUP.md
```

## 2. Configuración de la app

Ya está configurada para consultar:

```text
https://raw.githubusercontent.com/cienciaycienciaficcion-eng/AgendaTucuman/main/datos
```

No hace falta modificar `remote.ts`.

## 3. Probar GitHub Actions

En GitHub:

**Actions → Actualizar datos Agenda Tucumán → Run workflow**

El workflow ejecutará los tres extractores y actualizará:

- `datos/agenda_eventos.json`
- `datos/cine_cinemacenter_tucuman.json`
- `datos/cine_tucuman.json`
- `datos/radio_tucuman.json`

## 4. Funcionamiento

La app intenta obtener los datos actuales desde GitHub.

Si no hay conexión o GitHub no responde, utiliza los datos incluidos dentro de la aplicación como respaldo.

El workflow está programado para ejecutarse cada 6 horas y también puede ejecutarse manualmente.


## Información cinematográfica (Cinemacenter)

La información de las películas de Cinemacenter se genera dentro del mismo extractor que obtiene la cartelera.

El flujo es:

1. Descargar la cartelera oficial semanal de Tucumán.
2. Obtener los `movieId` internos mediante `seleccionarMovie(...)`.
3. Consultar `ajax_movieSlider.php` con ese ID.
4. Abrir la ficha oficial `/ficha/{movieId}-...`.
5. Extraer la metadata disponible en la ficha.

No se necesita `TMDB_API_TOKEN` para la información de Cinemacenter. Tampoco se utilizan IMDb, Google, Jina ni coincidencias externas.

Si Cinemacenter no publica un campo, se deja vacío/null.

### Licencia y atribución

TMDB indica que su API es gratuita para usos no comerciales siempre que se atribuya TMDB. Para proyectos
comerciales se requiere una licencia comercial. La aplicación debe incluir la atribución indicada por
TMDB y su logo aprobado. Antes de monetizar la aplicación o convertirla en un proyecto comercial, revisar
las condiciones vigentes de TMDB.

Aviso requerido por TMDB:

> This product uses the TMDB API but is not endorsed or certified by TMDB.

Fuente oficial: https://developer.themoviedb.org/docs/faq

## Resúmenes automáticos con Gemini

El workflow `Actualizar datos Agenda Tucumán` puede generar un resumen breve de las descripciones largas usando Gemini antes de publicar `datos/agenda_eventos.json`.

### Configurar la clave

En GitHub:

1. Abrir **Settings → Secrets and variables → Actions**.
2. Crear un **Repository secret** llamado `GEMINI_API_KEY`.
3. Pegar allí la clave creada en Google AI Studio.
4. No guardar la clave en el repositorio, en archivos Python, en `app.json` ni dentro de la APK.

El workflow utiliza por defecto el modelo `gemini-3.5-flash-lite`.

### Funcionamiento

- La descripción original se conserva completa.
- Solo se envían a Gemini las descripciones suficientemente largas para justificar un resumen.
- Si la descripción no cambió, se reutiliza el resumen anterior y no se vuelve a consultar Gemini.
- Cada resumen guarda `summary_source_hash` para identificar la versión del texto que fue resumida.
- Si Gemini falla, la actualización de la agenda no se pierde: se conserva el resumen anterior cuando existe y, para eventos nuevos, el resumen queda vacío.
- El campo `summary` queda disponible para la aplicación móvil y la URL original continúa en `url`.
